// 계산 핵심부. 파이썬 data_io.py, model.py, classify.py, interpret.py, calc_trace.py와 같은 식·같은 순서로 계산한다.
// 브라우저와 Node(테스트) 양쪽에서 쓴다. 서버나 외부 API를 쓰지 않는다.

export const DISCLAIMER = "수학 탐구 모델의 결과이며 실제 복약 판단이 아니다.";
export const INCREASE = "증강";
export const DECREASE = "감소";
export const INDEPENDENT = "독립";

const SUM_TOL = 1e-9;
const DRUG_KEYS = ["name", "dose_ratio", "metabolism", "inhibits", "induces", "actions"];
const ACTION_TYPES = ["agonist", "antagonist"];
const PK_KEYS = ["F", "dose", "CL", "tau"];
const TYPE_KO = { agonist: "작용제", antagonist: "차단제" };

export class DataError extends Error {}

// ---------------------------------------------------------------- 파이썬과 같은 합과 숫자 표시

// 파이썬 3.12+ sum()과 같은 보정 합(Neumaier). 같은 입력이면 같은 비트의 결과가 나온다.
export function pySum(xs) {
  if (xs.length === 0) return 0;
  let f = 0 + xs[0];
  let c = 0;
  for (let i = 1; i < xs.length; i++) {
    const x = xs[i];
    const t = f + x;
    if (Math.abs(f) >= Math.abs(x)) c += (f - t) + x;
    else c += (x - t) + f;
    f = t;
  }
  if (c !== 0 && Number.isFinite(c)) f += c;
  return f;
}

// 실수의 정확한 십진 전개: a = ds × 10^(−frac)
function exactDigits(a) {
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, a);
  const hi = view.getUint32(0);
  const lo = view.getUint32(4);
  const expBits = (hi >>> 20) & 0x7ff;
  let mant = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo);
  let e2;
  if (expBits === 0) e2 = -1074;
  else { mant |= 1n << 52n; e2 = expBits - 1075; }
  if (e2 >= 0) return { ds: (mant << BigInt(e2)).toString(), frac: 0 };
  return { ds: (mant * 5n ** BigInt(-e2)).toString(), frac: -e2 };
}

// 앞에서 keep자리만 남기고 반올림(짝수 쪽으로). 결과 자릿수는 keep 또는 keep+1(올림).
function roundHead(ds, keep) {
  if (keep >= ds.length) return ds + "0".repeat(keep - ds.length);
  if (keep < 0) return "";
  const head = ds.slice(0, keep);
  const rest = ds.slice(keep);
  const first = rest[0];
  const lastOdd = head.length > 0 && Number(head[head.length - 1]) % 2 === 1;
  const up = first > "5" || (first === "5" && (/[1-9]/.test(rest.slice(1)) || lastOdd));
  if (!up) return head;
  return (BigInt(head || "0") + 1n).toString().padStart(keep, "0");
}

// 파이썬 f"{x:.{d}f}"와 같은 표시
export function fmtFixed(x, d) {
  if (Number.isNaN(x)) return "nan";
  if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
  const neg = x < 0 || Object.is(x, -0);
  const a = Math.abs(x);
  let n = "0";
  if (a !== 0) {
    const { ds, frac } = exactDigits(a);
    if (d >= frac) n = ds + "0".repeat(d - frac);
    else n = roundHead(ds, ds.length - (frac - d)) || "0";
  }
  n = n.replace(/^0+(?=\d)/, "").padStart(d + 1, "0");
  const text = d > 0 ? `${n.slice(0, n.length - d)}.${n.slice(n.length - d)}` : n;
  return (neg ? "-" : "") + text;
}

// 파이썬 f"{x:.{p}g}"와 같은 표시
export function fmtG(x, p = 6) {
  if (Number.isNaN(x)) return "nan";
  if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
  if (x === 0) return Object.is(x, -0) ? "-0" : "0";
  const neg = x < 0;
  const { ds, frac } = exactDigits(Math.abs(x));
  let E = ds.length - 1 - frac;
  let head = roundHead(ds, p);
  if (head.length > p) { head = head.slice(0, p); E += 1; }
  let text;
  if (E < -4 || E >= p) {
    let mant = head[0] + (p > 1 ? "." + head.slice(1) : "");
    mant = mant.replace(/\.?0+$/, "");
    text = `${mant}e${E < 0 ? "-" : "+"}${String(Math.abs(E)).padStart(2, "0")}`;
  } else {
    let intPart;
    let fracPart;
    if (E >= 0) { intPart = head.slice(0, E + 1); fracPart = head.slice(E + 1); }
    else { intPart = "0"; fracPart = "0".repeat(-E - 1) + head; }
    fracPart = fracPart.replace(/0+$/, "");
    text = fracPart ? `${intPart}.${fracPart}` : intPart;
  }
  return (neg ? "-" : "") + text;
}

// ---------------------------------------------------------------- 표 (tables.py)

function charWidth(cp) {
  const wide = [[0x1100, 0x115f], [0x2e80, 0x303e], [0x3041, 0x33ff], [0x3400, 0x4dbf], [0x4e00, 0x9fff],
    [0xa000, 0xa4cf], [0xa960, 0xa97f], [0xac00, 0xd7a3], [0xf900, 0xfaff], [0xfe30, 0xfe4f],
    [0xff00, 0xff60], [0xffe0, 0xffe6], [0x1f300, 0x1f64f], [0x1f900, 0x1f9ff], [0x20000, 0x3fffd]];
  return wide.some(([a, b]) => cp >= a && cp <= b) ? 2 : 1;
}

function textWidth(text) {
  let w = 0;
  for (const ch of text) w += charWidth(ch.codePointAt(0));
  return w;
}

const pad = (text, width) => text + " ".repeat(width - textWidth(text));

function cell(v) {
  if (v === null || v === undefined) return "-";
  if (typeof v === "number") return fmtFixed(v, 4);
  return String(v);
}

export function formatTable(headers, rows, title) {
  const cells = rows.map((row) => row.map(cell));
  const widths = headers.map(textWidth);
  for (const row of cells) row.forEach((c, i) => { widths[i] = Math.max(widths[i], textWidth(c)); });
  const out = [];
  if (title) out.push(`[${title}]`);
  out.push(headers.map((h, i) => pad(h, widths[i])).join("  "));
  out.push(widths.map((w) => "-".repeat(w)).join("  "));
  if (!cells.length) out.push("(없음)");
  for (const row of cells) out.push(row.map((c, i) => pad(c, widths[i])).join("  "));
  return out.join("\n");
}

// ---------------------------------------------------------------- 입력 검사 (data_io.py)

const isDict = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const has = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);
const pyList = (xs) => `[${xs.map((x) => `'${x}'`).join(", ")}]`;
const pyNum = (v) => (Number.isInteger(v) ? v.toFixed(1) : String(v));

function num(item, key, where, warn, { lo = null, hi = null, loOpen = false, hiOpen = false } = {}) {
  if (!has(item, key) || item[key] === null) throw new DataError(`${where}: '${key}' 값이 없다`);
  const v = item[key];
  if (typeof v !== "number" || !Number.isFinite(v)) {
    throw new DataError(`${where}: '${key}'는 숫자여야 한다 (받은 값: ${JSON.stringify(v)})`);
  }
  if (lo !== null && (v < lo || (loOpen && v === lo))) {
    throw new DataError(`${where}: '${key}' = ${pyNum(v)} 범위 밖 (${loOpen ? ">" : "≥"} ${lo} 이어야 함)`);
  }
  if (hi !== null && (v > hi || (hiOpen && v === hi))) {
    throw new DataError(`${where}: '${key}' = ${pyNum(v)} 범위 밖 (${hiOpen ? "<" : "≤"} ${hi} 이어야 함)`);
  }
  return v;
}

function source(item, where, warn) {
  if (!has(item, "source")) throw new DataError(`${where}: 'source'(출처) 칸이 없다`);
  const src = item.source;
  if (typeof src !== "string") throw new DataError(`${where}: 'source'는 문자열이어야 한다`);
  if (!src.trim()) warn(`${where}: 출처(source)가 비어 있다`);
  return src;
}

function checkKeys(item, allowed, where, warn) {
  const extra = Object.keys(item).filter((k) => !allowed.includes(k) && !k.startsWith("_"));
  if (extra.length) warn(`${where}: 알 수 없는 칸 ${pyList(extra)}는 무시한다`);
}

function section(raw, key, where) {
  let sec = has(raw, key) ? raw[key] : {};
  if (sec === null) sec = {};
  if (!isDict(sec)) throw new DataError(`${where}: '${key}'는 {이름: 값} 형태여야 한다`);
  return sec;
}

function checkEnzyme(enz, enzymes, where) {
  if (enzymes && !enzymes.includes(enz)) {
    throw new DataError(`${where}: 허용되지 않은 효소 이름 '${enz}' (data/names.json 참고)`);
  }
}

export function parseDrug(raw, enzymes = null, warnings = []) {
  const warn = (m) => warnings.push(m);
  if (!isDict(raw)) throw new DataError("약 정보는 객체({...})여야 한다");
  const name = raw.name;
  if (typeof name !== "string" || !name.trim()) throw new DataError("약 'name'이 비어 있다");
  const where = `약 ${name}`;
  checkKeys(raw, DRUG_KEYS, where, warn);

  let doseRatio = 1.0;
  if (has(raw, "dose_ratio") && raw.dose_ratio !== null) {
    doseRatio = num(raw, "dose_ratio", where, warn, { lo: 0, loOpen: true });
  }
  const drug = { name, dose_ratio: doseRatio, metabolism: {}, inhibits: {}, induces: {}, actions: {} };

  for (const [enz, item] of Object.entries(section(raw, "metabolism", where))) {
    const w = `${where} metabolism.${enz}`;
    checkEnzyme(enz, enzymes, w);
    if (!isDict(item)) throw new DataError(`${w}: 값은 객체여야 한다`);
    checkKeys(item, ["f", "g", "source"], w, warn);
    const f = num(item, "f", w, warn, { lo: 0, hi: 1 });
    const g = num(item, "g", w, warn, { lo: 0, hi: 1 });
    if (f === 0 && g === 0) warn(`${w}: f, g가 모두 0인 원소는 적지 않는다`);
    drug.metabolism[enz] = { f, g, source: source(item, w, warn) };
  }
  const mets = Object.values(drug.metabolism);
  if (pySum(mets.map((m) => m.f)) > 1 + SUM_TOL) throw new DataError(`${where}: f의 합이 1보다 크다`);
  if (pySum(mets.map((m) => m.g)) > 1 + SUM_TOL) throw new DataError(`${where}: g의 합이 1보다 크다`);

  for (const [enz, item] of Object.entries(section(raw, "inhibits", where))) {
    const w = `${where} inhibits.${enz}`;
    checkEnzyme(enz, enzymes, w);
    if (!isDict(item)) throw new DataError(`${w}: 값은 객체여야 한다`);
    const direct = ["s", "t"].some((k) => has(item, k));
    const byKi = ["Ki", "conc_liver", "conc_gut"].some((k) => has(item, k));
    if (direct && byKi) throw new DataError(`${w}: s,t 방식과 Ki 방식을 함께 쓸 수 없다`);
    let s; let t; let given = null;
    if (byKi) {
      checkKeys(item, ["Ki", "conc_liver", "conc_gut", "source"], w, warn);
      const ki = num(item, "Ki", w, warn, { lo: 0, loOpen: true });
      const cl = num(item, "conc_liver", w, warn, { lo: 0 });
      const cg = num(item, "conc_gut", w, warn, { lo: 0 });
      const xl = cl / ki;
      const xg = cg / ki;
      s = xl / (1 + xl);
      t = xg / (1 + xg);
      given = { Ki: ki, conc_liver: cl, conc_gut: cg };
    } else {
      checkKeys(item, ["s", "t", "source"], w, warn);
      s = num(item, "s", w, warn, { lo: 0, hi: 1, hiOpen: true });
      t = num(item, "t", w, warn, { lo: 0, hi: 1, hiOpen: true });
    }
    if (s === 0 && t === 0) warn(`${w}: s, t가 모두 0인 원소는 적지 않는다`);
    drug.inhibits[enz] = { s, t, from_ki: byKi, ki_input: given, source: source(item, w, warn) };
  }

  for (const [enz, item] of Object.entries(section(raw, "induces", where))) {
    const w = `${where} induces.${enz}`;
    checkEnzyme(enz, enzymes, w);
    if (!isDict(item)) throw new DataError(`${w}: 값은 객체여야 한다`);
    checkKeys(item, ["u", "source"], w, warn);
    const u = num(item, "u", w, warn, { lo: 0 });
    if (u === 0) warn(`${w}: u가 0인 원소는 적지 않는다`);
    drug.induces[enz] = { u, source: source(item, w, warn) };
  }

  for (const [tgt, item] of Object.entries(section(raw, "actions", where))) {
    const w = `${where} actions.${tgt}`;
    if (!isDict(item)) throw new DataError(`${w}: 값은 객체여야 한다`);
    checkKeys(item, ["type", "c", "e", "source", ...PK_KEYS, "EC50", "KB"], w, warn);
    const typ = item.type;
    if (!ACTION_TYPES.includes(typ)) throw new DataError(`${w}: type은 'agonist' 또는 'antagonist'여야 한다`);
    const ways = [["c", ["c"]], ["e", ["e"]], ["pk", [...PK_KEYS, "EC50", "KB"]]]
      .filter(([, keys]) => keys.some((k) => has(item, k))).map(([n]) => n);
    if (ways.length !== 1) throw new DataError(`${w}: c, e, (F·dose·CL·tau·EC50/KB) 중 하나만 써야 한다`);
    const way = ways[0];
    let c; let given = null;
    if (way === "e") {
      if (typ !== "agonist") throw new DataError(`${w}: e는 작용제(agonist)에만 쓸 수 있다`);
      const e = num(item, "e", w, warn, { lo: 0, hi: 1, hiOpen: true });
      c = e / (1 - e);
      given = { e };
    } else if (way === "pk") {
      const [need, other] = typ === "agonist" ? ["EC50", "KB"] : ["KB", "EC50"];
      if (has(item, other)) {
        throw new DataError(`${w}: ${typ === "agonist" ? "작용제" : "차단제"}에는 ${need}를 쓴다(${other} 아님)`);
      }
      given = { F: num(item, "F", w, warn, { lo: 0, hi: 1, loOpen: true }) };
      for (const k of ["dose", "CL", "tau", need]) given[k] = num(item, k, w, warn, { lo: 0, loOpen: true });
      given.C = given.F * given.dose / (given.CL * given.tau);
      c = given.C / given[need];
    } else {
      c = num(item, "c", w, warn, { lo: 0 });
    }
    if (c === 0) warn(`${w}: 작용 세기가 0인 원소는 적지 않는다`);
    drug.actions[tgt] = { type: typ, c, from_e: way === "e", way, input: given, source: source(item, w, warn) };
  }
  return drug;
}

export function parseRules(raw, warnings = []) {
  const warn = (m) => warnings.push(m);
  if (!isDict(raw) || !isDict(raw.effects)) throw new DataError("규칙표에 'effects' 객체가 없다");
  const effects = {};
  for (const [name, item] of Object.entries(raw.effects)) {
    const w = `효과 ${name}`;
    if (!isDict(item)) throw new DataError(`${w}: 값은 객체여야 한다`);
    checkKeys(item, ["up", "down", "k", "threshold", "source"], w, warn);
    const lists = {};
    for (const key of ["up", "down"]) {
      const lst = has(item, key) ? item[key] : [];
      if (!Array.isArray(lst) || !lst.every((x) => typeof x === "string" && x)) {
        throw new DataError(`${w}: '${key}'는 대상 이름 목록이어야 한다`);
      }
      if (new Set(lst).size !== lst.length) throw new DataError(`${w}: '${key}'에 같은 대상이 두 번 있다`);
      lists[key] = [...lst];
    }
    const both = lists.up.filter((x) => lists.down.includes(x)).sort();
    if (both.length) warn(`${w}: ${pyList(both)}가 up과 down에 모두 있다`);
    if (!lists.up.length && !lists.down.length) warn(`${w}: up, down이 모두 비어 있다`);
    const k = (!has(item, "k") || item.k === null) ? 1.0 : num(item, "k", w, warn, { lo: 0 });
    let thr = has(item, "threshold") ? item.threshold : null;
    if (thr !== null) thr = num(item, "threshold", w, warn, { lo: 0, loOpen: true });
    effects[name] = { up: lists.up, down: lists.down, k, threshold: thr, source: source(item, w, warn) };
  }
  return { effects };
}

export function ruleTargets(rules) {
  const out = new Set();
  for (const eff of Object.values(rules.effects)) {
    eff.up.forEach((t) => out.add(t));
    eff.down.forEach((t) => out.add(t));
  }
  return out;
}

export function checkTargets(drugs, rules, warnings = []) {
  const known = ruleTargets(rules);
  for (const d of drugs) {
    for (const tgt of Object.keys(d.actions)) {
      if (!known.has(tgt)) warnings.push(`약 ${d.name}: 대상 '${tgt}'는 규칙표의 어느 효과에도 없다(효과 계산에서 빠짐)`);
    }
  }
  return warnings;
}

// ---------------------------------------------------------------- 계산 식 (model.py)

export const cFromE = (e) => {
  if (!(e >= 0 && e < 1)) throw new RangeError(`e = ${e}는 0 ≤ e < 1이어야 한다`);
  return e / (1 - e);
};
export const eFromC = (c) => c / (1 + c);
export const sFromKi = (conc, ki) => { const x = conc / ki; return x / (1 + x); };
export const pkConcentration = (F, dose, CL, tau) => F * dose / (CL * tau);
export const cFromPk = (F, dose, CL, tau, ec50OrKb) => pkConcentration(F, dose, CL, tau) / ec50OrKb;

export function scaleInhibition(s, doseRatio) {
  if (doseRatio === 1) return s;
  const x = s / (1 - s) * doseRatio;
  return x / (1 + x);
}

export function remainingActivity(inhibitions, inductions) {
  let a = 1.0;
  for (const s of inhibitions) a *= 1 - s;
  for (const u of inductions) a *= 1 + u;
  return a;
}

export function rFromFractions(parts) {
  const total = pySum(parts.map(([f]) => f));
  return 1 / (pySum(parts.map(([f, a]) => f * a)) + (1 - total));
}

export function enzymeRemaining(drug, others) {
  const out = {};
  for (const enz of Object.keys(drug.metabolism)) {
    const sList = []; const tList = []; const uList = []; const inhibitors = []; const inducers = [];
    for (const o of others) {
      if (o.name === drug.name) continue;
      const inh = o.inhibits[enz];
      if (inh) {
        const s = scaleInhibition(inh.s, o.dose_ratio);
        const t = scaleInhibition(inh.t, o.dose_ratio);
        sList.push(s); tList.push(t); inhibitors.push([o.name, s, t]);
      }
      const ind = o.induces[enz];
      if (ind) { uList.push(ind.u); inducers.push([o.name, ind.u]); }
    }
    out[enz] = {
      f: drug.metabolism[enz].f, g: drug.metabolism[enz].g,
      a_liver: remainingActivity(sList, uList), a_gut: remainingActivity(tList, uList),
      inhibitors, inducers,
    };
  }
  return out;
}

export function concentrationRatio(drug, others) {
  const rem = enzymeRemaining(drug, others);
  const met = Object.entries(drug.metabolism);
  const rLiver = rFromFractions(met.map(([e, m]) => [m.f, rem[e].a_liver]));
  const rGut = rFromFractions(met.map(([e, m]) => [m.g, rem[e].a_gut]));
  return { r_liver: rLiver, r_gut: rGut, r: rLiver * rGut, enzymes: rem };
}

export function targetEffect(cAgonists, cAntagonists = []) {
  const cAg = pySum(cAgonists);
  const cAnt = pySum(cAntagonists);
  return cAg / (1 + cAg + cAnt);
}

export function targetActions(drugs, rMap = null) {
  const out = {};
  for (const d of drugs) {
    const r = rMap === null ? 1.0 : rMap[d.name];
    for (const [tgt, act] of Object.entries(d.actions)) {
      const c2 = act.c * r * d.dose_ratio;
      if (!out[tgt]) out[tgt] = { ag: [], ant: [] };
      out[tgt][act.type === "agonist" ? "ag" : "ant"].push([d.name, c2]);
    }
  }
  for (const slot of Object.values(out)) {
    slot.E = targetEffect(slot.ag.map(([, c]) => c), slot.ant.map(([, c]) => c));
  }
  return out;
}

export function combineSum(cs, k) {
  if (k === 0) return pySum(cs);
  let prod = 1.0;
  for (const c of cs) prod *= 1 + k * c;
  return (prod - 1) / k;
}

export const combine = (eList, k) => eFromC(combineSum(eList.map((e) => e / (1 - e)), k));
export const effectValue = (upE, downE, k) => combine(upE, k) - combine(downE, k);

export function effectFromTargets(rule, eMap, k) {
  const up = rule.up.map((t) => (has(eMap, t) ? eMap[t] : 0.0));
  const down = rule.down.map((t) => (has(eMap, t) ? eMap[t] : 0.0));
  return effectValue(up, down, k);
}

export function inhibitionRoots(f, g, R) {
  if (R <= 0) throw new RangeError("R은 0보다 커야 한다");
  const rhs = 1 - 1 / R;
  if (f * g === 0) {
    if (f + g === 0) throw new RangeError("f, g가 모두 0이면 억제 정도를 구할 수 없다");
    return [rhs / (f + g)];
  }
  const a = f * g; const b = -(f + g); const c = rhs;
  const disc = b * b - 4 * a * c;
  if (disc < 0) throw new RangeError(`R = ${R}을 만드는 실수 s가 없다`);
  const sq = Math.sqrt(disc);
  return [(-b - sq) / (2 * a), (-b + sq) / (2 * a)];
}

export function invertInhibition(f, g, R) {
  const valid = inhibitionRoots(f, g, R).filter((s) => s >= 0 && s < 1);
  if (!valid.length) throw new RangeError(`f = ${f}, g = ${g}, R = ${R}에서 0 ≤ s < 1인 근이 없다`);
  return valid[0];
}

// ---------------------------------------------------------------- 분류 (classify.py)

function pairs(xs) {
  const out = [];
  for (let i = 0; i < xs.length; i++) for (let j = i + 1; j < xs.length; j++) out.push([xs[i], xs[j]]);
  return out;
}

const sorted = (xs) => [...xs].sort();

export function classify(drugs, rules) {
  const concentration = [];
  for (const a of drugs) {
    const changers = new Set([...Object.keys(a.inhibits), ...Object.keys(a.induces)]);
    for (const b of drugs) {
      if (a.name === b.name) continue;
      const common = sorted(Object.keys(b.metabolism).filter((e) => changers.has(e)));
      if (!common.length) continue;
      const how = common.map((enz) => {
        const kinds = [["억제", "inhibits"], ["유도", "induces"]].filter(([, sec]) => has(a[sec], enz)).map(([k]) => k);
        return `${enz}(${kinds.join("+")})`;
      });
      concentration.push({ from: a.name, to: b.name, enzymes: common, how });
    }
  }
  const sameTarget = [];
  for (const [a, b] of pairs(drugs)) {
    for (const tgt of sorted(Object.keys(a.actions).filter((t) => has(b.actions, t)))) {
      const ta = a.actions[tgt].type; const tb = b.actions[tgt].type;
      let label = "차단제 낌";
      if (ta === "agonist" && tb === "agonist") label = "작용제끼리";
      else if (ta === "antagonist" && tb === "antagonist") label = "차단제끼리";
      sameTarget.push({ a: a.name, b: b.name, target: tgt, types: [ta, tb], label });
    }
  }
  const direction = (rule, tgt) => ["up", "down"].filter((d) => rule[d].includes(tgt)).join("+");
  const sameEffect = [];
  for (const [a, b] of pairs(drugs)) {
    for (const [eff, rule] of Object.entries(rules.effects)) {
      const linked = new Set([...rule.up, ...rule.down]);
      for (const p of sorted(Object.keys(a.actions).filter((t) => linked.has(t)))) {
        for (const q of sorted(Object.keys(b.actions).filter((t) => linked.has(t)))) {
          if (p === q) continue;
          const dp = direction(rule, p); const dq = direction(rule, q);
          sameEffect.push({ a: a.name, b: b.name, effect: eff, target_a: p, target_b: q, dir_a: dp, dir_b: dq, same_dir: dp === dq });
        }
      }
    }
  }
  return { concentration, same_target: sameTarget, same_effect: sameEffect };
}

export function formatClassification(cls) {
  return [
    formatTable(["바꾸는 약", "바뀌는 약", "겹친 효소"],
      cls.concentration.map((c) => [c.from, c.to, c.how.join(", ")]),
      "분류 1: 평균 농도를 바꾸는 순서쌍 (A → B)"),
    formatTable(["약 1", "약 2", "같은 대상", "종류"],
      cls.same_target.map((s) => [s.a, s.b, s.target, `${s.label} (${TYPE_KO[s.types[0]]}·${TYPE_KO[s.types[1]]})`]),
      "분류 2: 같은 대상"),
    formatTable(["약 1", "약 2", "효과", "대상 1", "대상 2", "방향"],
      cls.same_effect.map((s) => [s.a, s.b, s.effect, `${s.target_a}(${s.dir_a})`, `${s.target_b}(${s.dir_b})`,
        s.same_dir ? "같은 방향" : "반대 방향"]),
      "분류 3: 서로 다른 대상, 같은 효과"),
  ].join("\n\n");
}

// ---------------------------------------------------------------- 판정 (interpret.py)

export function drugRatios(drugs) {
  const out = {};
  for (const d of drugs) out[d.name] = concentrationRatio(d, drugs);
  return out;
}

export function effectValues(drugs, rules, rMap = null, ruleK = true) {
  const tacts = targetActions(drugs, rMap);
  const eMap = {};
  for (const [t, v] of Object.entries(tacts)) eMap[t] = v.E;
  const vals = {};
  for (const [eff, rule] of Object.entries(rules.effects)) vals[eff] = effectFromTargets(rule, eMap, ruleK ? rule.k : 1.0);
  return [vals, tacts];
}

export function judge(b0, bfull, cfg) {
  const j = cfg.judgement;
  if (Math.abs(b0) >= j.b0_small) {
    const R = bfull / b0;
    if (R > j.ratio_up) return [INCREASE, R, null];
    if (R < j.ratio_down) return [DECREASE, R, null];
    return [INDEPENDENT, R, null];
  }
  const sign = b0 < 0 ? -1.0 : 1.0;
  const d = (bfull - b0) * sign;
  if (Math.abs(d) < j.diff_small) return [INDEPENDENT, null, d];
  return [d > 0 ? INCREASE : DECREASE, null, d];
}

export function causeLabel(verdict, rContrib, kContrib, cfg) {
  if (verdict === INDEPENDENT) return "-";
  const lim = cfg.judgement.cause_min;
  const parts = [["r", rContrib], ["k", kContrib]].filter(([, v]) => Math.abs(v) >= lim).map(([n]) => n);
  return parts.length ? parts.join("+") : "없음";
}

export function manifestation(rule, singles, b0, bfull) {
  const thr = rule.threshold;
  if (thr === null) return [null, "-"];
  const over = Object.entries(singles).filter(([, v]) => Math.abs(v) >= thr).map(([n]) => n);
  if (over.length) return [false, `단독으로 이미 기준 이상(${over.join(", ")})`];
  if (Math.abs(bfull) < thr) return [false, "기준 미만"];
  if (Math.abs(b0) >= thr) return [true, "더하기만으로 발현"];
  return [true, "상호작용 때문에 발현"];
}

export function rFlag(r, cfg) {
  if (r >= cfg.flag.r_high) return "평균 농도 증가";
  if (r <= cfg.flag.r_low) return "평균 농도 감소";
  return null;
}

export function analyze(drugs, rules, cfg, warnings = null) {
  if (warnings) checkTargets(drugs, rules, warnings);
  const ratios = drugRatios(drugs);
  for (const info of Object.values(ratios)) info.flag = rFlag(info.r, cfg);
  const rMap = {};
  for (const [n, v] of Object.entries(ratios)) rMap[n] = v.r;

  const [b0Vals, t0] = effectValues(drugs, rules, null, false);
  const [brVals] = effectValues(drugs, rules, rMap, false);
  const [bfVals, tf] = effectValues(drugs, rules, rMap, true);
  const singles = {};
  for (const d of drugs) singles[d.name] = effectValues([d], rules, null, true)[0];

  const effects = [];
  for (const [eff, rule] of Object.entries(rules.effects)) {
    const b0 = b0Vals[eff]; const br = brVals[eff]; const bf = bfVals[eff];
    const [verdict, R, d] = judge(b0, bf, cfg);
    const rC = br - b0; const kC = bf - br;
    const targets = {};
    for (const direction of ["up", "down"]) {
      for (const t of rule[direction]) {
        if (has(tf, t)) targets[t] = { dir: direction, E0: t0[t].E, E: tf[t].E, ag: tf[t].ag, ant: tf[t].ant };
      }
    }
    const involved = sorted(new Set(Object.values(targets).flatMap((t) => [...t.ag, ...t.ant].map(([n]) => n))));
    const effSingles = {};
    for (const n of involved) effSingles[n] = singles[n][eff];
    const [shown, kind] = manifestation(rule, effSingles, b0, bf);
    effects.push({
      effect: eff, rule, B0: b0, Br: br, Bfull: bf, verdict, R, d, r_contrib: rC, k_contrib: kC,
      cause: causeLabel(verdict, rC, kC, cfg), manifest: shown, manifest_kind: kind,
      singles: effSingles, targets, involved,
    });
  }
  return { drugs: drugs.map((d) => d.name), classification: classify(drugs, rules), ratios, effects };
}

// ---------------------------------------------------------------- 계산 과정 (calc_trace.py)

const MINUS = "−";

export function traceNum(x) {
  let text = fmtG(x, 4);
  if (text === "-0" || text === "-0.0") text = "0";
  return text.replaceAll("-", MINUS);
}

const par = (x) => (x < 0 ? `(${traceNum(x)})` : traceNum(x));

class Trace {
  constructor() { this.lines = []; }
  h(level, text) {
    if (this.lines.length && this.lines[this.lines.length - 1] !== "") this.lines.push("");
    this.lines.push(`${"#".repeat(level)} ${text}`, "");
  }
  eq(text) { this.lines.push(`- ${text}`); }
  raw(text) { this.lines.push(text); }
  last() { return this.lines[this.lines.length - 1]; }
  text() { return `${this.lines.join("\n").trim()}\n`; }
}

function inputSection(t, drugs) {
  const n_ = traceNum;
  t.h(2, "0. 입력 변환");
  const before = t.lines.length;
  for (const d of drugs) {
    const n = d.name;
    for (const [tgt, act] of Object.entries(d.actions)) {
      const g = act.input;
      if (act.way === "e") {
        t.eq(`c(${n}, ${tgt}) = e ÷ (1 − e) = ${n_(g.e)} ÷ (1 − ${n_(g.e)}) = ${n_(act.c)}`);
      } else if (act.way === "pk") {
        const key = act.type === "agonist" ? "EC50" : "KB";
        t.eq(`C(${n}) = F × dose ÷ (CL × tau) = ${n_(g.F)} × ${n_(g.dose)} ÷ (${n_(g.CL)} × ${n_(g.tau)}) = ${n_(g.C)}`);
        t.eq(`c(${n}, ${tgt}) = C ÷ ${key} = ${n_(g.C)} ÷ ${n_(g[key])} = ${n_(act.c)}`);
      }
    }
    for (const [enz, inh] of Object.entries(d.inhibits)) {
      const g = inh.ki_input;
      if (g) {
        for (const [site, conc, val] of [["간", "conc_liver", inh.s], ["장", "conc_gut", inh.t]]) {
          const x = g[conc] / g.Ki;
          t.eq(`x_${site}(${n}, ${enz}) = ${conc} ÷ Ki = ${n_(g[conc])} ÷ ${n_(g.Ki)} = ${n_(x)}, `
            + `${site === "간" ? "s" : "t"} = x ÷ (1 + x) = ${n_(x)} ÷ (1 + ${n_(x)}) = ${n_(val)}`);
        }
      }
      if (d.dose_ratio !== 1) {
        for (const key of ["s", "t"]) {
          const v = inh[key];
          const x = v / (1 - v) * d.dose_ratio;
          t.eq(`${key}(${n}, ${enz}, 용량 ${n_(d.dose_ratio)}배): x = ${key} ÷ (1 − ${key}) × dose_ratio = `
            + `${n_(v)} ÷ (1 − ${n_(v)}) × ${n_(d.dose_ratio)} = ${n_(x)}, `
            + `${key} = x ÷ (1 + x) = ${n_(scaleInhibition(v, d.dose_ratio))}`);
        }
      }
    }
  }
  if (t.lines.length === before) t.eq("변환할 입력 없음 (c, s, t를 직접 입력)");
}

function ratioSection(t, drugs) {
  const n_ = traceNum;
  t.h(2, "2. 효소별 남은 작용 a_간, a_장");
  const infos = {};
  for (const d of drugs) {
    const info = concentrationRatio(d, drugs);
    infos[d.name] = info;
    t.h(3, d.name);
    if (!Object.keys(d.metabolism).length) { t.eq("분해 효소 정보 없음"); continue; }
    for (const [enz, rem] of Object.entries(info.enzymes)) {
      if (!rem.inhibitors.length && !rem.inducers.length) {
        t.eq(`a_간(${enz}) = a_장(${enz}) = 1 (억제·유도하는 다른 약 없음)`);
        continue;
      }
      const who = [...rem.inhibitors.map(([n]) => `${n} 억제`), ...rem.inducers.map(([n]) => `${n} 유도`)];
      for (const [site, key, idx] of [["간", "a_liver", 1], ["장", "a_gut", 2]]) {
        const factors = [...rem.inhibitors.map((x) => `(1 − ${n_(x[idx])})`), ...rem.inducers.map(([, u]) => `(1 + ${n_(u)})`)];
        t.eq(`a_${site}(${enz}) = ${factors.join(" × ")} = ${n_(rem[key])}  ← ${who.join(", ")}`);
      }
    }
  }
  t.h(2, "3. 평균 농도 변화 r_간, r_장, r");
  for (const d of drugs) {
    const n = d.name;
    const info = infos[n];
    const rem = info.enzymes;
    if (!Object.values(rem).some((r) => r.inhibitors.length || r.inducers.length)) {
      t.eq(`r_간(${n}) = r_장(${n}) = r(${n}) = 1 (분해 효소를 바꾸는 다른 약 없음)`);
      continue;
    }
    for (const [site, frac, key, val] of [["간", "f", "a_liver", info.r_liver], ["장", "g", "a_gut", info.r_gut]]) {
      const enzs = Object.keys(rem);
      const terms = enzs.map((e) => `${n_(rem[e][frac])} × ${n_(rem[e][key])}`);
      const rest = 1 - pySum(enzs.map((e) => rem[e][frac]));
      t.eq(`r_${site}(${n}) = 1 ÷ (${terms.join(" + ")} + ${n_(Math.max(rest, 0.0))}) = ${n_(val)}`);
    }
    t.eq(`r(${n}) = r_간 × r_장 = ${n_(info.r_liver)} × ${n_(info.r_gut)} = ${n_(info.r)}`);
  }
  const rMap = {};
  for (const [n, v] of Object.entries(infos)) rMap[n] = v.r;
  return rMap;
}

function targetLines(t, drugs, rMap, only = null) {
  const n_ = traceNum;
  const byName = {};
  for (const d of drugs) byName[d.name] = d;
  const tacts = targetActions(drugs, rMap);
  for (const tgt of sorted(Object.keys(tacts))) {
    if (only !== null && !only.has(tgt)) continue;
    const slot = tacts[tgt];
    for (const [name, c2] of [...slot.ag, ...slot.ant]) {
      const d = byName[name];
      const r = rMap === null ? 1.0 : rMap[name];
      const kind = d.actions[tgt].type === "agonist" ? "작용제" : "차단제";
      t.eq(`c′(${name}, ${tgt}, ${kind}) = c × r × dose_ratio = ${n_(d.actions[tgt].c)} × ${n_(r)} × ${n_(d.dose_ratio)} = ${n_(c2)}`);
    }
    const cAg = pySum(slot.ag.map(([, c]) => c));
    const cAnt = pySum(slot.ant.map(([, c]) => c));
    for (const [label, items, total] of [["C_ag", slot.ag, cAg], ["C_ant", slot.ant, cAnt]]) {
      if (items.length > 1) t.eq(`${label}(${tgt}) = ${items.map(([, c]) => n_(c)).join(" + ")} = ${n_(total)}`);
      else t.eq(`${label}(${tgt}) = ${n_(total)}`);
    }
    t.eq(`E(${tgt}) = C_ag ÷ (1 + C_ag + C_ant) = ${n_(cAg)} ÷ (1 + ${n_(cAg)} + ${n_(cAnt)}) = ${n_(slot.E)}`);
  }
  const eMap = {};
  for (const [tg, v] of Object.entries(tacts)) eMap[tg] = v.E;
  return eMap;
}

function groupLines(t, label, targets, eMap, k) {
  const n_ = traceNum;
  const get = (tg) => (has(eMap, tg) ? eMap[tg] : 0.0);
  const present = targets.filter((tg) => get(tg) > 0).map((tg) => [tg, eMap[tg]]);
  const absent = targets.filter((tg) => get(tg) === 0);
  if (!present.length) { t.eq(`${label} 묶음 작용 = 0 (작용하는 대상 없음)`); return 0.0; }
  const cs = [];
  for (const [tg, e] of present) {
    const c = e / (1 - e);
    cs.push(c);
    t.eq(`c(${tg}) = E ÷ (1 − E) = ${n_(e)} ÷ (1 − ${n_(e)}) = ${n_(c)}`);
  }
  const cSum = combineSum(cs, k);
  if (cs.length === 1) t.eq(`c_합(${label}) = c(${present[0][0]}) = ${n_(cSum)} (대상 1개)`);
  else if (k === 0) t.eq(`c_합(${label}) = ${cs.map(n_).join(" + ")} = ${n_(cSum)} (k = 0)`);
  else {
    const prod = cs.map((c) => `(1 + ${n_(k)} × ${n_(c)})`).join(" × ");
    t.eq(`c_합(${label}) = (${prod} − 1) ÷ ${n_(k)} = ${n_(cSum)}`);
  }
  const act = eFromC(cSum);
  t.eq(`${label} 묶음 작용 = c_합 ÷ (1 + c_합) = ${n_(cSum)} ÷ (1 + ${n_(cSum)}) = ${n_(act)}`);
  if (absent.length) t.eq(`(작용하는 약이 없는 대상 ${absent.join(", ")}는 E = 0이라 뺌)`);
  return act;
}

function effectLines(t, rule, eMap, k, symbol) {
  const up = groupLines(t, "up", rule.up, eMap, k);
  const down = rule.down.length ? groupLines(t, "down", rule.down, eMap, k) : 0.0;
  if (!rule.down.length) t.eq("down 묶음 작용 = 0 (down 대상 없음)");
  const val = up - down;
  t.eq(`${symbol} = (up 묶음 작용) − (down 묶음 작용) = ${traceNum(up)} − ${par(down)} = ${traceNum(val)}`);
  return val;
}

export function buildTrace(drugs, rules, cfg, res) {
  const n_ = traceNum;
  const j = cfg.judgement;
  const t = new Trace();
  t.raw(`# 계산 과정: ${drugs.map((d) => d.name).join(" + ")}`);
  inputSection(t, drugs);

  t.h(2, "1. 분류");
  t.raw("```");
  t.raw(formatClassification(res.classification));
  t.raw("```");

  const rMap = ratioSection(t, drugs);
  const effects = res.effects.filter((e) => e.involved.length);
  const used = new Set(effects.flatMap((e) => [...e.rule.up, ...e.rule.down]));

  t.h(2, "4. 대상별 작용 C_ag, C_ant, E_P");
  t.h(3, "기준 (모든 r = 1)");
  const e0 = targetLines(t, drugs, null, used);
  t.h(3, "실제 (r 반영)");
  const ef = targetLines(t, drugs, rMap, used);

  t.h(2, "5. 효과별 합치기 cᵢ, c_합, 묶음 작용");
  const values = {};
  for (const e of effects) {
    const rule = e.rule;
    const down = rule.down.join(", ") || "없음";
    t.h(3, `${e.effect} (up: ${rule.up.join(", ")} / down: ${down}, 규칙표 k = ${n_(rule.k)})`);
    t.raw("**B₀ (r = 1, k = 1)**");
    t.raw("");
    const b0 = effectLines(t, rule, e0, 1.0, "B₀");
    t.raw("");
    t.raw("**B_r (실제 r, k = 1)**");
    t.raw("");
    const br = effectLines(t, rule, ef, 1.0, "B_r");
    t.raw("");
    t.raw(`**B_full (실제 r, k = ${n_(rule.k)})**`);
    t.raw("");
    const bf = effectLines(t, rule, ef, rule.k, "B_full");
    values[e.effect] = [b0, br, bf];
  }

  t.h(2, "6. B₀, B_r, B_full과 판정");
  for (const e of effects) {
    const [b0, br, bf] = values[e.effect];
    t.h(3, e.effect);
    t.eq(`B₀ = ${n_(b0)}, B_r = ${n_(br)}, B_full = ${n_(bf)}`);
    if (Math.abs(b0) >= j.b0_small) {
      t.eq(`|B₀| = ${n_(Math.abs(b0))} ≥ ${n_(j.b0_small)} → 비율로 판정`);
      const R = bf / b0;
      t.eq(`R = B_full ÷ B₀ = ${n_(bf)} ÷ ${par(b0)} = ${n_(R)}`);
      if (R > j.ratio_up) t.eq(`R = ${n_(R)} > ${n_(j.ratio_up)} → ${e.verdict}`);
      else if (R < j.ratio_down) t.eq(`R = ${n_(R)} < ${n_(j.ratio_down)} → ${e.verdict}`);
      else t.eq(`${n_(j.ratio_down)} ≤ R = ${n_(R)} ≤ ${n_(j.ratio_up)} → ${e.verdict}`);
    } else {
      const sign = b0 < 0 ? -1 : 1;
      const d = (bf - b0) * sign;
      t.eq(`|B₀| = ${n_(Math.abs(b0))} < ${n_(j.b0_small)} → 차이로 판정`);
      t.eq(`d = (B_full − B₀) × 부호(B₀) = (${n_(bf)} − ${par(b0)}) × ${par(sign)} = ${n_(d)}`);
      if (Math.abs(d) < j.diff_small) t.eq(`|d| = ${n_(Math.abs(d))} < ${n_(j.diff_small)} → ${e.verdict}`);
      else t.eq(`|d| = ${n_(Math.abs(d))} ≥ ${n_(j.diff_small)}, d ${d > 0 ? "> 0" : "< 0"} → ${e.verdict}`);
    }
    t.eq(`r 기여 = B_r − B₀ = ${n_(br)} − ${par(b0)} = ${n_(br - b0)}`);
    t.eq(`k 기여 = B_full − B_r = ${n_(bf)} − ${par(br)} = ${n_(bf - br)}`);
    if (e.verdict === INDEPENDENT) t.eq("원인: - (판정이 독립)");
    else t.eq(`원인: |기여| ≥ ${n_(j.cause_min)}인 것 → ${e.cause}`);
  }

  t.h(2, "7. 발현");
  for (const e of effects) {
    const rule = e.rule;
    const thr = rule.threshold;
    t.h(3, e.effect);
    if (thr === null) { t.eq("threshold 없음 → 판정하지 않음"); continue; }
    for (const n of e.involved) {
      const d = drugs.find((x) => x.name === n);
      if (t.last() !== "") t.raw("");
      t.raw(`**단독(${n})**`);
      t.raw("");
      const eSingle = targetLines(t, [d], null, new Set([...rule.up, ...rule.down]));
      effectLines(t, rule, eSingle, rule.k, `단독(${n})`);
    }
    t.raw("");
    const singles = Object.entries(e.singles);
    const over = singles.filter(([, v]) => Math.abs(v) >= thr).map(([n]) => n);
    const listing = singles.map(([n, v]) => `${n} ${n_(Math.abs(v))}`).join(", ");
    if (over.length) {
      t.eq(`|단독 값| = ${listing} → ${over.join(", ")}가 ${n_(thr)} 이상 → 발현 아님(단독으로 이미 기준 이상)`);
      continue;
    }
    t.eq(`|단독 값| = ${listing} → 모두 < ${n_(thr)}`);
    const bf = e.Bfull; const b0 = e.B0;
    if (Math.abs(bf) < thr) { t.eq(`|B_full| = ${n_(Math.abs(bf))} < ${n_(thr)} → 발현 아님`); continue; }
    t.eq(`|B_full| = ${n_(Math.abs(bf))} ≥ ${n_(thr)} → 발현`);
    if (Math.abs(b0) >= thr) t.eq(`|B₀| = ${n_(Math.abs(b0))} ≥ ${n_(thr)} → 더하기만으로 발현`);
    else t.eq(`|B₀| = ${n_(Math.abs(b0))} < ${n_(thr)} → 상호작용 때문에 발현`);
  }

  t.raw("");
  t.raw(DISCLAIMER);
  return [t.text(), values];
}

// ---------------------------------------------------------------- 약물 집합 읽기

// 붙여 넣은 글에서 JSON 부분만 꺼낸다(AI가 ```json 블록이나 설명 문장을 함께 줘도 됨).
export function extractJson(text) {
  const trimmed = text.trim();
  if (!trimmed) throw new DataError("입력이 비어 있다");
  try { return JSON.parse(trimmed); } catch { /* 아래에서 다시 시도 */ }
  const fence = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) { try { return JSON.parse(fence[1]); } catch { /* 아래에서 다시 시도 */ } }
  const start = trimmed.search(/[[{]/);
  const end = Math.max(trimmed.lastIndexOf("}"), trimmed.lastIndexOf("]"));
  if (start >= 0 && end > start) {
    const body = trimmed.slice(start, end + 1);
    try { return JSON.parse(body); } catch (err) {
      // AI가 자주 남기는 끝 쉼표({"a": 1,})만 고쳐서 한 번 더 읽어 본다
      try { return JSON.parse(body.replace(/,(\s*[}\]])/g, "$1")); } catch { /* 아래 오류로 */ }
      throw new DataError(`JSON 형식 오류: ${err.message}. AI 답의 코드 블록을 처음부터 끝까지 빠짐없이 복사했는지 확인하세요`);
    }
  }
  throw new DataError("JSON을 찾지 못했다. AI 답의 ```json 코드 블록을 통째로 붙여 넣으세요");
}

// AI가 찾지 못한 값 목록("missing")을 {drug, item, reason}으로 맞춘다.
function parseMissing(raw, warnings) {
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) {
    warnings.push("'missing'은 목록이어야 한다(무시함)");
    return [];
  }
  const out = [];
  for (const m of raw) {
    if (typeof m === "string" && m.trim()) out.push({ drug: "", item: m.trim(), reason: "" });
    else if (isDict(m)) {
      const text = (k) => (typeof m[k] === "string" ? m[k].trim() : "");
      if (text("drug") || text("item") || text("reason")) out.push({ drug: text("drug"), item: text("item"), reason: text("reason") });
    } else warnings.push(`'missing'의 항목 ${JSON.stringify(m)}를 읽지 못했다(무시함)`);
  }
  return out;
}

// 기준 용량 목록("dose_basis")을 {drug, dose, source}로 맞춘다.
function parseDoseBasis(raw, warnings) {
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) {
    warnings.push("'dose_basis'는 목록이어야 한다(무시함)");
    return [];
  }
  const out = [];
  for (const m of raw) {
    if (!isDict(m)) { warnings.push(`'dose_basis'의 항목 ${JSON.stringify(m)}를 읽지 못했다(무시함)`); continue; }
    const text = (k) => (typeof m[k] === "string" ? m[k].trim() : (typeof m[k] === "number" ? String(m[k]) : ""));
    if (text("drug") || text("dose")) out.push({ drug: text("drug"), dose: text("dose"), source: text("source") });
  }
  return out;
}

// 약물 집합: {"drugs": [...], "rules": {"effects": {...}}, "dose_basis": [...], "missing": [...]} 또는 [약, ...]
export function parseSet(raw, enzymes, fallbackRules = null) {
  const warnings = [];
  let rawDrugs; let rawRules = null; let missing = []; let doseBasis = [];
  if (Array.isArray(raw)) rawDrugs = raw;
  else if (isDict(raw)) {
    rawDrugs = raw.drugs;
    rawRules = isDict(raw.rules) ? raw.rules : (isDict(raw.effects) ? { effects: raw.effects } : null);
    missing = parseMissing(raw.missing, warnings);
    doseBasis = parseDoseBasis(raw.dose_basis, warnings);
  }
  if (!Array.isArray(rawDrugs)) throw new DataError("약 목록(drugs)을 찾을 수 없다");
  const drugs = rawDrugs.map((d) => parseDrug(d, enzymes, warnings));
  const seen = new Set();
  for (const d of drugs) {
    if (seen.has(d.name)) throw new DataError(`약 이름 '${d.name}'이 중복되었다`);
    seen.add(d.name);
  }
  let rules;
  let usedFallback = false;
  if (rawRules) rules = parseRules(rawRules, warnings);
  else if (fallbackRules) {
    rules = parseRules(fallbackRules, []);
    usedFallback = true;
    warnings.push("입력에 규칙표(rules)가 없어 기본 예시 규칙표를 썼다. 실제 약이라면 rules도 함께 넣어야 한다");
  } else throw new DataError("규칙표(rules)가 없다");
  return { drugs, rules, warnings, usedFallback, missing, doseBasis };
}

// ---------------------------------------------------------------- 데이터가 충분한지

// 출처 칸으로 값의 종류를 나눈다: 출처 있음 / 추정값("추정"으로 시작, 추측 모드) / 가정값(virtual, "가정"으로 시작) / 출처 빈칸
export function sourceKind(src) {
  const text = (src || "").trim();
  if (!text) return "empty";
  if (text.startsWith("추정")) return "estimated";
  if (/^virtual$/i.test(text) || text.startsWith("가정")) return "assumed";
  return "cited";
}

export const NO_DATA = "데이터가 없어서 계산하지 못했다";

// 고른 약과 규칙표로 (가) 평균 농도 변화와 (나) 작용의 겹침을 계산할 자료가 있는지 본다.
// 계산 식은 바꾸지 않고, 자료가 없어서 r = 1이나 효과 0이 나온 것을 결과처럼 보이지 않게 하려는 것이다.
export function assessData(drugs, rules) {
  const known = ruleTargets(rules);
  const perDrug = drugs.map((d) => ({
    name: d.name,
    metabolism: Object.keys(d.metabolism).length,
    inhibits: Object.keys(d.inhibits).length,
    induces: Object.keys(d.induces).length,
    actions: Object.keys(d.actions).length,
    linked: Object.keys(d.actions).filter((t) => known.has(t)).length,
  }));
  const values = { cited: 0, estimated: 0, assumed: 0, empty: 0 };
  for (const d of drugs) {
    for (const sec of ["metabolism", "inhibits", "induces", "actions"]) {
      for (const item of Object.values(d[sec])) values[sourceKind(item.source)] += 1;
    }
  }
  for (const eff of Object.values(rules.effects)) values[sourceKind(eff.source)] += 1;

  // (가) 평균 농도 변화
  const pairs = classify(drugs, rules).concentration;
  const withMet = perDrug.filter((p) => p.metabolism > 0).map((p) => p.name);
  const withMod = perDrug.filter((p) => p.inhibits + p.induces > 0).map((p) => p.name);
  const canMeet = withMod.some((a) => withMet.some((b) => a !== b));
  const conc = { notes: [] };
  if (pairs.length) {
    conc.status = "ok";
    conc.text = `계산했다: 효소가 겹친 순서쌍 ${pairs.length}개`;
  } else if (!canMeet) {
    conc.status = "nodata";
    const why = [];
    if (!withMet.length) why.push("분해 효소(metabolism) 자료가 있는 약이 없다");
    if (!withMod.length) why.push("억제·유도(inhibits·induces) 자료가 있는 약이 없다");
    if (!why.length) why.push("다른 약을 억제·유도하는 약과, 분해 효소 자료가 있는 약이 같은 약 하나뿐이다");
    conc.text = `${NO_DATA}: ${why.join(", ")}`;
  } else {
    conc.status = "none";
    conc.text = "계산했다: 입력된 효소가 서로 겹치지 않아 평균 농도 변화가 없다(r = 1)";
  }
  const noMet = perDrug.filter((p) => p.metabolism === 0).map((p) => p.name);
  if (conc.status !== "nodata" && noMet.length) {
    conc.notes.push(`${noMet.join(", ")}: 분해 효소 자료가 없어 r을 계산하지 못했다(r = 1로 둠)`);
  }

  // (나) 작용의 겹침
  const effect = { notes: [] };
  const ruleCount = Object.values(rules.effects).filter((r) => r.up.length || r.down.length).length;
  const withAct = perDrug.filter((p) => p.actions > 0).map((p) => p.name);
  const withLink = perDrug.filter((p) => p.linked > 0).map((p) => p.name);
  if (!ruleCount) {
    effect.status = "nodata";
    effect.text = `${NO_DATA}: 규칙표(rules)에 효과가 없다`;
  } else if (!withAct.length) {
    effect.status = "nodata";
    effect.text = `${NO_DATA}: 작용 대상(actions) 자료가 있는 약이 없다`;
  } else if (!withLink.length) {
    effect.status = "nodata";
    effect.text = `${NO_DATA}: 약의 작용 대상이 규칙표의 어느 효과와도 연결되지 않는다`;
  } else {
    effect.status = "ok";
    effect.text = `계산했다: 작용 대상이 규칙표와 연결된 약 ${withLink.length}개`;
    const out = perDrug.filter((p) => p.linked === 0).map((p) => p.name);
    if (out.length) effect.notes.push(`${out.join(", ")}: 규칙표와 연결된 작용 대상 자료가 없어 효과 계산에서 빠졌다`);
    if (withLink.length === 1) effect.notes.push("효과에 관여하는 약이 하나뿐이라, 같은 대상·같은 효과에서 작용이 겹칠 수 없다");
  }

  const bad = [conc, effect].filter((x) => x.status === "nodata").length;
  const overall = bad === 2 ? "nodata" : (bad === 1 ? "partial" : "ok");
  return { perDrug, values, conc, effect, overall, noMetabolism: noMet };
}
