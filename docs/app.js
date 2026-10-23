// 화면 처리. 계산은 모두 core.js(파이썬과 같은 식)로 한다.
import * as core from "./core.js";
import { CONFIG, DEMO_SET, ENZYMES } from "./data.js";
import { MAKE_PROMPT, READ_PROMPT, RESULT_SLOT } from "./prompts.js";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const STORE_KEY = "dic.input.v1";
const TABS = ["calc", "prompts", "rules", "tutorial", "install"];

const state = {
  raw: null,        // 붙여 넣은 JSON
  set: null,        // 검사한 약물 집합 {drugs, rules, warnings, usedFallback}
  selected: new Set(),
  drugs: [],        // 고른 약
  result: null,
  assess: null,     // 데이터가 충분한지
  trace: "",
};

// ---------------------------------------------------------------- 공통

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const f4 = (x) => (x === null || x === undefined ? "-" : core.fmtFixed(x, 4));
const g6 = (x) => core.fmtG(x, 6);

function storeGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function storeSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* 저장이 막혀 있어도 계산은 된다 */ }
}

let toastTimer = null;
function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
}

async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text);
    toast(`${label} 복사했어요`);
    return;
  } catch { /* 아래 방법으로 다시 시도 */ }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  ta.setSelectionRange(0, text.length);
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  ta.remove();
  toast(ok ? `${label} 복사했어요` : "복사하지 못했어요. 글을 길게 눌러 직접 복사하세요");
}

function download(name, text) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function table(headers, rows, numericCols = [], wrapCols = []) {
  const head = headers.map((h) => `<th>${esc(h)}</th>`).join("");
  const body = rows.map((r) => `<tr>${r.map((c, i) => {
    const cls = numericCols.includes(i) ? ' class="n"' : (wrapCols.includes(i) ? ' class="wrap"' : "");
    return `<td${cls}>${c}</td>`;
  }).join("")}</tr>`).join("");
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

// ---------------------------------------------------------------- 탭

function showTab(name) {
  if (!TABS.includes(name)) name = "calc";
  for (const t of TABS) $(`#tab-${t}`).hidden = t !== name;
  $$(".tabs button").forEach((b) => {
    const on = b.dataset.tab === name;
    b.setAttribute("aria-selected", String(on));
    if (on) b.scrollIntoView({ block: "nearest", inline: "nearest" });
  });
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  window.scrollTo({ top: 0 });
}

// ---------------------------------------------------------------- 입력과 계산

function showMessages(errors, warnings) {
  const parts = [];
  if (errors.length) {
    parts.push(`<div class="msg err"><b>입력 오류</b><ul>${errors.map((e) => `<li>${esc(e)}</li>`).join("")}</ul></div>`);
  }
  if (warnings.length) {
    const list = `<ul>${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>`;
    parts.push(warnings.length > 4
      ? `<details class="msg warn"><summary>경고 ${warnings.length}개 (계산은 됐지만 확인하세요)</summary>${list}</details>`
      : `<div class="msg warn"><b>경고</b> (계산은 됐지만 확인하세요)${list}</div>`);
  }
  $("#messages").innerHTML = parts.join("");
}

function readInput({ quiet = false } = {}) {
  const text = $("#input").value;
  storeSet(STORE_KEY, text);
  if (!text.trim()) {
    state.set = null;
    $("#pick-card").hidden = true;
    $("#result-card").hidden = true;
    if (!quiet) showMessages(["입력이 비어 있어요. JSON을 붙여 넣거나 「예시 넣기」를 눌러 보세요"], []);
    renderRules();
    return;
  }
  try {
    state.raw = core.extractJson(text);
    state.set = core.parseSet(state.raw, ENZYMES, DEMO_SET.rules);
  } catch (err) {
    state.set = null;
    $("#pick-card").hidden = true;
    $("#result-card").hidden = true;
    showMessages([err.message], []);
    renderRules();
    return;
  }
  state.selected = new Set(state.set.drugs.map((d) => d.name));
  renderPick();
  renderRules();
  compute();
  if (!quiet) $("#pick-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderPick() {
  $("#pick-card").hidden = false;
  $("#pick").innerHTML = state.set.drugs.map((d, i) => `
    <label><input type="checkbox" data-i="${i}" ${state.selected.has(d.name) ? "checked" : ""}>${esc(d.name)}</label>`).join("");
}

function compute() {
  const set = state.set;
  state.drugs = set.drugs.filter((d) => state.selected.has(d.name));
  const warnings = [...set.warnings];
  if (state.drugs.length < 2) {
    $("#pick-msg").textContent = "함께 먹을 약을 2개 이상 골라 주세요.";
    $("#result-card").hidden = true;
    state.result = null;
    $("#copy-read-2").disabled = true;
    showMessages([], warnings);
    return;
  }
  $("#pick-msg").textContent = `${state.drugs.length}개를 함께 먹는 경우를 골랐어요.`;
  try {
    state.result = core.analyze(state.drugs, set.rules, CONFIG, warnings);
    [state.trace] = core.buildTrace(state.drugs, set.rules, CONFIG, state.result);
    state.assess = core.assessData(state.drugs, set.rules);
  } catch (err) {
    showMessages([`계산 중 오류: ${err.message}`], warnings);
    $("#result-card").hidden = true;
    return;
  }
  showMessages([], warnings);
  renderResult();
  $("#result-card").hidden = false;
  $("#copy-read-2").disabled = false;
}

const VERDICT_CLASS = { [core.INCREASE]: "up", [core.DECREASE]: "down", [core.INDEPENDENT]: "ind" };

const STATUS_CLASS = { ok: "ok", none: "ok", nodata: "nodata" };

function dataStatusHtml(a) {
  const v = a.values;
  const total = v.cited + v.assumed + v.empty;
  const line = (label, part) => `<li class="${STATUS_CLASS[part.status]}"><b>${label}</b>: ${esc(part.text)}${
    part.notes.length ? `<ul>${part.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}</li>`;
  const head = {
    ok: "계산에 필요한 자료가 있어요",
    partial: "일부는 데이터가 없어서 계산하지 못했어요",
    nodata: "데이터가 없어서 계산하지 못했어요",
  }[a.overall];
  const valueLine = total
    ? `입력된 값 ${total}개: 출처 있음 ${v.cited}개, 가정값(virtual·가정) ${v.assumed}개, 출처 빈칸 ${v.empty}개`
    : "입력된 값이 하나도 없어요";
  const missing = state.set.missing;
  const missingHtml = missing.length
    ? `<details><summary>AI가 찾지 못한 값 ${missing.length}개</summary><ul>${missing.map((m) =>
      `<li>${esc([m.drug, m.item].filter(Boolean).join(" · "))}${m.reason ? ` <span class="muted">(${esc(m.reason)})</span>` : ""}</li>`).join("")}</ul></details>`
    : "";
  return `<div class="status ${a.overall}">
    <p class="status-head">${head}</p>
    <ul class="status-list">${line("(가) 평균 농도 변화", a.conc)}${line("(나) 작용의 겹침", a.effect)}</ul>
    <p class="muted">${esc(valueLine)}</p>
    ${missingHtml}
  </div>`;
}

function coverageTable(a) {
  const cell = (n) => (n ? `${n}개` : '<span class="none">없음</span>');
  return table(["약", "분해 효소", "억제", "유도", "작용 대상", "규칙표와 연결"], a.perDrug.map((p) => [
    esc(p.name), cell(p.metabolism), cell(p.inhibits), cell(p.induces), cell(p.actions), cell(p.linked)]));
}

function renderResult() {
  const res = state.result;
  const a = state.assess;
  const out = [];
  out.push(`<p>함께 먹는 약: <b>${res.drugs.map(esc).join(", ")}</b></p>`);
  out.push(dataStatusHtml(a));
  $("#trace-box").hidden = a.overall === "nodata";

  if (a.overall === "nodata") {
    out.push('<p class="section-title">약마다 입력된 자료</p>');
    out.push(coverageTable(a));
    out.push(`<p class="hint">값을 지어내지 않고 계산을 멈췄어요. 출처가 있는 값을 찾아 넣거나,
      연습이라면 source를 "virtual"로 적은 가정값을 넣어 보세요.</p>`);
    $("#result").innerHTML = out.join("");
    $("#trace").innerHTML = "";
    return;
  }

  out.push('<p class="section-title">평균 농도 변화 r</p>');
  if (a.conc.status === "nodata") {
    out.push(`<p class="nodata-line">${esc(a.conc.text)}</p>`);
  } else {
    const noMet = new Set(a.noMetabolism);
    out.push(table(["약", "r_간", "r_장", "r", "표시"], res.drugs.map((n) => {
      const v = res.ratios[n];
      if (noMet.has(n)) return [esc(n), "", "", '<span class="none">자료 없음</span>', '<span class="muted">분해 효소 자료 없음</span>'];
      return [esc(n), f4(v.r_liver), f4(v.r_gut), `<b>${f4(v.r)}</b>`, v.flag ? `<span class="badge ${v.flag.includes("증가") ? "up" : "down"}">${v.flag}</span>` : ""];
    }), [1, 2, 3]));
  }
  const flagged = res.drugs.filter((n) => res.ratios[n].flag);
  if (flagged.length) {
    out.push(`<ul class="flags">${flagged.map((n) => `<li>${esc(n)}: r = ${f4(res.ratios[n].r)} → ${res.ratios[n].flag}
      (기준 r ≥ ${CONFIG.flag.r_high} 또는 r ≤ ${CONFIG.flag.r_low})</li>`).join("")}</ul>`);
  }

  const effects = res.effects.filter((e) => e.involved.length);
  out.push('<p class="section-title">효과별 결과</p>');
  if (a.effect.status === "nodata") {
    out.push(`<p class="nodata-line">${esc(a.effect.text)}</p>`);
  } else if (!effects.length) {
    out.push('<p class="hint">고른 약이 작용하는 효과가 규칙표에 없어요. 규칙표 탭과 경고를 확인하세요.</p>');
  } else {
    out.push(table(["효과", "관련 약", "B₀", "B_r", "B_full", "R 또는 d", "판정", "원인", "발현"], effects.map((e) => {
      const rd = e.R !== null ? `R = ${f4(e.R)}` : `d = ${f4(e.d)}`;
      const shown = e.manifest === null ? "-" : `${e.manifest ? "<b>발현</b>" : "아님"}<br><span class="muted">${esc(e.manifest_kind)}</span>`;
      return [esc(e.effect), esc(e.involved.join(", ")), f4(e.B0), f4(e.Br), `<b>${f4(e.Bfull)}</b>`, rd,
        `<span class="badge ${VERDICT_CLASS[e.verdict]}">${e.verdict}</span>`,
        `<b>${esc(e.cause)}</b><br><span class="muted">r ${f4(e.r_contrib)}<br>k ${f4(e.k_contrib)}</span>`, shown];
    }), [2, 3, 4, 5], [1, 7, 8]));
  }
  const untouched = res.effects.filter((e) => !e.involved.length).map((e) => e.effect);
  if (untouched.length && a.effect.status !== "nodata") {
    out.push(`<p class="hint">고른 약이 작용하지 않는 효과: ${untouched.map(esc).join(", ")}</p>`);
  }
  if (a.conc.status === "nodata" && a.effect.status !== "nodata") {
    out.push('<p class="hint">(가) 평균 농도 변화는 자료가 없어 반영하지 못했어요(모든 r = 1로 계산). 그래서 B_r = B₀이고 원인 r은 나올 수 없어요.</p>');
  }
  out.push('<details><summary>약마다 입력된 자료</summary>' + coverageTable(a) + "</details>");

  const cls = res.classification;
  const typeKo = { agonist: "작용제", antagonist: "차단제" };
  out.push(`<details><summary>분류 (이름이 겹친 곳)</summary>
    <p class="section-title">평균 농도를 바꾸는 순서쌍 (A → B)</p>
    ${cls.concentration.length ? table(["바꾸는 약", "바뀌는 약", "겹친 효소"], cls.concentration.map((c) => [esc(c.from), esc(c.to), esc(c.how.join(", "))])) : '<p class="hint">없음</p>'}
    <p class="section-title">같은 대상</p>
    ${cls.same_target.length ? table(["약 1", "약 2", "같은 대상", "종류"], cls.same_target.map((s) => [esc(s.a), esc(s.b), esc(s.target), `${s.label} (${typeKo[s.types[0]]}·${typeKo[s.types[1]]})`])) : '<p class="hint">없음</p>'}
    <p class="section-title">서로 다른 대상, 같은 효과</p>
    ${cls.same_effect.length ? table(["약 1", "약 2", "효과", "대상 1", "대상 2", "방향"], cls.same_effect.map((s) => [esc(s.a), esc(s.b), esc(s.effect), esc(`${s.target_a}(${s.dir_a})`), esc(`${s.target_b}(${s.dir_b})`), s.same_dir ? "같은 방향" : "반대 방향"])) : '<p class="hint">없음</p>'}
  </details>`);

  $("#result").innerHTML = out.join("");
  $("#trace").innerHTML = renderMarkdown(state.trace);
}

// 계산 과정(마크다운)을 화면용 HTML로
function renderMarkdown(md) {
  const html = [];
  let inList = false;
  let inCode = false;
  let code = [];
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const closeList = () => { if (inList) { html.push("</ul>"); inList = false; } };
  for (const line of md.split("\n")) {
    if (line.startsWith("```")) {
      if (inCode) { html.push(`<pre>${esc(code.join("\n"))}</pre>`); code = []; inCode = false; } else { closeList(); inCode = true; }
      continue;
    }
    if (inCode) { code.push(line); continue; }
    if (line.startsWith("- ")) {
      if (!inList) { html.push("<ul>"); inList = true; }
      html.push(`<li>${inline(line.slice(2))}</li>`);
      continue;
    }
    closeList();
    const h = line.match(/^(#{1,3}) (.*)$/);
    if (h) html.push(`<h${h[1].length + 2}>${inline(h[2])}</h${h[1].length + 2}>`);
    else if (line.trim()) html.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  return html.join("\n");
}

// AI 해석용 결과 글
function statusText(a) {
  const v = a.values;
  const lines = [`(가) 평균 농도 변화: ${a.conc.text}`, ...a.conc.notes.map((n) => `  - ${n}`),
    `(나) 작용의 겹침: ${a.effect.text}`, ...a.effect.notes.map((n) => `  - ${n}`),
    `입력된 값: 출처 있음 ${v.cited}개, 가정값(virtual·가정) ${v.assumed}개, 출처 빈칸 ${v.empty}개`];
  const missing = state.set.missing;
  if (missing.length) {
    lines.push("AI가 찾지 못한 값:");
    for (const m of missing) lines.push(`  - ${[m.drug, m.item].filter(Boolean).join(" · ")}${m.reason ? ` (${m.reason})` : ""}`);
  }
  lines.push("", core.formatTable(["약", "분해 효소", "억제", "유도", "작용 대상", "규칙표와 연결"],
    a.perDrug.map((p) => [p.name, String(p.metabolism), String(p.inhibits), String(p.induces), String(p.actions), String(p.linked)]),
    "약마다 입력된 자료 개수"));
  return lines.join("\n");
}

function resultText() {
  const res = state.result;
  const a = state.assess;
  const names = new Set(res.drugs);
  const rawDrugs = (Array.isArray(state.raw) ? state.raw : state.raw.drugs).filter((d) => d && names.has(d.name));
  const rawRules = state.set.usedFallback ? DEMO_SET.rules : (state.raw.rules || { effects: state.raw.effects });
  const input = JSON.stringify({ drugs: rawDrugs, rules: rawRules }, null, 2);
  if (a.overall === "nodata") {
    return ["[입력한 약물 집합]", input, "", "[데이터 상태]", `${core.NO_DATA}.`, statusText(a), "",
      "[결과 요약]", `함께 먹는 약: ${res.drugs.join(", ")}`, `${core.NO_DATA}. 계산 결과 없음.`, "", core.DISCLAIMER].join("\n");
  }
  const rTable = core.formatTable(["약", "r_간", "r_장", "r", "평균 농도 변화"],
    res.drugs.map((n) => [n, res.ratios[n].r_liver, res.ratios[n].r_gut, res.ratios[n].r, res.ratios[n].flag || ""]),
    "평균 농도 변화 r");
  const effects = res.effects.filter((e) => e.involved.length);
  const eTable = core.formatTable(
    ["효과", "관련 약", "B0", "B_r", "B_full", "R 또는 d", "판정", "r 기여", "k 기여", "원인", "threshold", "발현", "발현 구분"],
    effects.map((e) => [e.effect, e.involved.join(" "), e.B0, e.Br, e.Bfull,
      e.R !== null ? `R=${f4(e.R)}` : `d=${f4(e.d)}`, e.verdict, e.r_contrib, e.k_contrib, e.cause,
      e.rule.threshold === null ? "-" : g6(e.rule.threshold),
      e.manifest === null ? "-" : (e.manifest ? "발현" : "아님"), e.manifest_kind]),
    "효과별 결과");
  const noMet = new Set(a.noMetabolism);
  return [
    "[입력한 약물 집합]",
    input,
    "",
    "[데이터 상태]",
    statusText(a),
    "",
    "[결과 요약]",
    `함께 먹는 약: ${res.drugs.join(", ")}`,
    "",
    a.conc.status === "nodata" ? `[평균 농도 변화 r]\n${a.conc.text}`
      : rTable + (noMet.size ? `\n(분해 효소 자료가 없어 r을 계산하지 못한 약: ${[...noMet].join(", ")}. 위 표의 1.0000은 계산값이 아님)` : ""),
    "",
    a.effect.status === "nodata" ? `[효과별 결과]\n${a.effect.text}` : eTable,
    "",
    "[계산 과정]",
    state.trace.trim(),
  ].join("\n");
}

// ---------------------------------------------------------------- 규칙표

function kMeaning(k) {
  if (k === 0) return "같은 대상처럼 더함";
  if (k === 1) return "서로 따로 작용";
  if (k > 1) return "서로 도움(시너지)";
  return "일부 겹침";
}

function renderRules() {
  let rules;
  let origin;
  if (state.set) {
    rules = state.set.rules;
    origin = state.set.usedFallback ? "(입력에 rules가 없어 기본 예시 규칙표 사용)" : "(입력한 약물 집합의 규칙표)";
  } else {
    rules = core.parseRules(DEMO_SET.rules, []);
    origin = "(기본 예시 규칙표, 가상)";
  }
  $("#rules-origin").textContent = origin;
  const rows = Object.entries(rules.effects).map(([name, r]) => [
    esc(name), esc(r.up.join(", ") || "-"), esc(r.down.join(", ") || "-"),
    `${g6(r.k)} <span class="muted">${kMeaning(r.k)}</span>`,
    r.threshold === null ? '<span class="muted">없음</span>' : g6(r.threshold),
    `<span class="wrap">${esc(r.source || "(비어 있음)")}</span>`,
  ]);
  $("#rules-table").innerHTML = rows.length
    ? table(["효과", "올리는 대상(up)", "내리는 대상(down)", "k", "threshold", "출처"], rows)
    : '<p class="hint">효과가 없어요.</p>';

  const j = CONFIG.judgement;
  $("#config-table").innerHTML = table(["항목", "값", "뜻"], [
    ["비율 판정", `${j.ratio_down} / ${j.ratio_up}`, `|B₀| ≥ ${j.b0_small}이면 R = B_full ÷ B₀. R > ${j.ratio_up} 증강, R < ${j.ratio_down} 감소, 그 사이 독립`],
    ["차이 판정", `${j.diff_small}`, `|B₀| < ${j.b0_small}이면 d = (B_full − B₀) × (B₀의 부호). |d| < ${j.diff_small}이면 독립`],
    ["원인 표시", `${j.cause_min}`, `|r 기여| 또는 |k 기여|가 ${j.cause_min} 이상이면 원인으로 표시`],
    ["평균 농도 변화", `${CONFIG.flag.r_low} / ${CONFIG.flag.r_high}`, `r ≥ ${CONFIG.flag.r_high} 또는 r ≤ ${CONFIG.flag.r_low}이면 따로 표시`],
  ].map(([a, b, c]) => [esc(a), esc(b), `<span class="wrap">${esc(c)}</span>`]));
}

// ---------------------------------------------------------------- 튜토리얼

let tutStep = 0;
function showStep(i) {
  const steps = $$("#tab-tutorial .step");
  tutStep = Math.max(0, Math.min(steps.length - 1, i));
  steps.forEach((s, k) => { s.hidden = k !== tutStep; });
  $$("#tut-dots button").forEach((b, k) => {
    if (k === tutStep) b.setAttribute("aria-current", "step");
    else b.removeAttribute("aria-current");
  });
  $("#tut-count").textContent = `${tutStep + 1} / ${steps.length}`;
  $("#tut-prev").disabled = tutStep === 0;
  $("#tut-next").textContent = tutStep === steps.length - 1 ? "계산하러 가기" : "다음";
}

function setupTutorial() {
  const steps = $$("#tab-tutorial .step");
  $("#tut-dots").innerHTML = steps.map((s, k) => `<li><button data-step="${k}">${k + 1}. ${esc(s.dataset.title)}</button></li>`).join("");
  $("#tut-dots").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-step]");
    if (b) showStep(Number(b.dataset.step));
  });
  $("#tut-prev").addEventListener("click", () => showStep(tutStep - 1));
  $("#tut-next").addEventListener("click", () => {
    if (tutStep === steps.length - 1) showTab("calc");
    else showStep(tutStep + 1);
  });
  const j = CONFIG.judgement;
  const fill = {
    flag: `r ≥ ${CONFIG.flag.r_high} 또는 r ≤ ${CONFIG.flag.r_low}`,
    ratio: `|B₀| ≥ ${j.b0_small}이면 R = B_full ÷ B₀로 보고 R > ${j.ratio_up} 증강, R < ${j.ratio_down} 감소, 그 사이 독립. `
      + `|B₀|가 더 작으면 d = (B_full − B₀) × (B₀의 부호)로 보고 |d| < ${j.diff_small}이면 독립`,
    cause: `|기여| ≥ ${j.cause_min}인 것을 원인으로 표시 (r: 평균 농도 변화 때문, k: 대상끼리 돕거나 겹쳐서)`,
  };
  $$("[data-cfg]").forEach((el) => { el.textContent = fill[el.dataset.cfg]; });
  showStep(0);
}

// ---------------------------------------------------------------- 앱 설치

function detectDevice() {
  const ua = navigator.userAgent;
  if (/Android/i.test(ua)) return "android";
  if (/iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return "ipad";
  if (/iPhone|iPod/.test(ua)) return "iphone";
  return null;
}

let installEvent = null;
function setupInstall() {
  const url = `${location.origin}${location.pathname}`;
  $("#app-url").textContent = url;
  $("#copy-url").addEventListener("click", () => copyText(url, "주소를"));
  const device = detectDevice();
  $$(".device").forEach((card) => {
    const here = card.dataset.device === device;
    card.classList.toggle("current", here);
    card.querySelector(".here").hidden = !here;
  });
  if (device) {
    const card = $(`.device[data-device="${device}"]`);
    card.parentNode.insertBefore(card, $$(".device")[0]);
  }
  const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  if (standalone) {
    $("#install-state").hidden = false;
    $("#install-state").textContent = "이미 앱으로 설치해서 열고 있어요.";
  }
  window.addEventListener("beforeinstallprompt", (ev) => {
    ev.preventDefault();
    installEvent = ev;
    $("#install-btn").hidden = false;
  });
  $("#install-btn").addEventListener("click", async () => {
    if (!installEvent) return;
    installEvent.prompt();
    await installEvent.userChoice;
    installEvent = null;
    $("#install-btn").hidden = true;
  });
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(() => { /* 오프라인 기능이 없어도 앱은 쓸 수 있다 */ });
  }
}

// ---------------------------------------------------------------- 시작

function loadExample() {
  $("#input").value = JSON.stringify(DEMO_SET, null, 2);
  readInput();
}

function init() {
  $$(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  document.addEventListener("click", (ev) => {
    const go = ev.target.closest("[data-goto]");
    if (go) showTab(go.dataset.goto);
    const act = ev.target.closest("[data-action='try-example']");
    if (act) { showTab("calc"); loadExample(); }
  });
  window.addEventListener("hashchange", () => showTab(location.hash.slice(1)));

  $("#run").addEventListener("click", () => readInput());
  $("#example").addEventListener("click", loadExample);
  $("#clear").addEventListener("click", () => {
    $("#input").value = "";
    readInput({ quiet: true });
    $("#messages").innerHTML = "";
  });
  $("#file").addEventListener("change", async (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    $("#input").value = await file.text();
    ev.target.value = "";
    readInput();
  });

  $("#pick").addEventListener("change", (ev) => {
    const box = ev.target.closest("input[data-i]");
    if (!box) return;
    const name = state.set.drugs[Number(box.dataset.i)].name;
    if (box.checked) state.selected.add(name); else state.selected.delete(name);
    compute();
  });
  $("#pick-all").addEventListener("click", () => { state.selected = new Set(state.set.drugs.map((d) => d.name)); renderPick(); compute(); });
  $("#pick-none").addEventListener("click", () => { state.selected = new Set(); renderPick(); compute(); });

  $("#copy-trace").addEventListener("click", () => copyText(state.trace, "계산 과정을"));
  $("#save-trace").addEventListener("click", () => download(`계산과정_${state.drugs.map((d) => d.name).join("+")}.md`, state.trace));
  const copyRead = () => copyText(READ_PROMPT.replace(RESULT_SLOT, resultText()), "해석 프롬프트와 결과를");
  $("#copy-read").addEventListener("click", copyRead);
  $("#copy-read-2").addEventListener("click", copyRead);
  $("#copy-result").addEventListener("click", () => copyText(`${resultText()}\n`, "결과를"));

  $("#make-prompt").value = MAKE_PROMPT;
  $("#read-prompt").value = READ_PROMPT;
  $("#copy-make").addEventListener("click", () => copyText(MAKE_PROMPT, "입력 만들기 프롬프트를"));
  $("#copy-read-empty").addEventListener("click", () => copyText(READ_PROMPT, "해석 프롬프트를"));

  $("#enzymes").innerHTML = ENZYMES.map((e) => `<span>${esc(e)}</span>`).join("");
  setupTutorial();
  setupInstall();
  renderRules();

  const saved = storeGet(STORE_KEY);
  if (saved && saved.trim()) {
    $("#input").value = saved;
    readInput({ quiet: true });
  }
  showTab(location.hash.slice(1) || "calc");
}

init();
