// 웹앱 계산 핵심부 테스트: 파이썬 tests/와 같은 입력·같은 기대값(허용 오차 1e-3)
import assert from "node:assert/strict";
import { test } from "node:test";

import * as core from "../docs/core.js";
import { CONFIG, ENZYMES } from "../docs/data.js";

const TOL = 1e-3;
const near = (actual, expected) =>
  assert.ok(Math.abs(actual - expected) <= TOL, `${actual} ≠ ${expected} (허용 오차 ${TOL})`);

const mk = (name, { metabolism = {}, inhibits = {}, induces = {}, actions = {}, dose_ratio = 1 } = {}) =>
  ({ name, dose_ratio, metabolism, inhibits, induces, actions });
const met = (f, g = 0) => ({ f, g, source: "virtual" });
const inh = (s, t = 0) => ({ s, t, source: "virtual" });

test("T1 간: f=0.7, s=0.6 → r_간 = 1.7241", () => {
  const b = mk("B", { metabolism: { CYP3A: met(0.7) } });
  const a = mk("A", { inhibits: { CYP3A: inh(0.6) } });
  near(core.concentrationRatio(b, [a]).r_liver, 1.7241);
});

test("T2 간+장: g=0.5, t=0.8 → r_장 = 1.6667, r = 2.8736", () => {
  const b = mk("B", { metabolism: { CYP3A: met(0.7, 0.5) } });
  const a = mk("A", { inhibits: { CYP3A: inh(0.6, 0.8) } });
  const res = core.concentrationRatio(b, [a]);
  near(res.r_liver, 1.7241);
  near(res.r_gut, 1.6667);
  near(res.r, 2.8736);
});

test("T3 같은 효소를 s=0.5인 약 두 개가 억제 → r = 2.5", () => {
  const b = mk("B", { metabolism: { CYP3A: met(0.8) } });
  const others = [mk("A1", { inhibits: { CYP3A: inh(0.5) } }), mk("A2", { inhibits: { CYP3A: inh(0.5) } })];
  near(core.concentrationRatio(b, others).r, 2.5);
});

test("T4 유도: f=0.5, u=1 → r = 0.6667", () => {
  const b = mk("B", { metabolism: { CYP3A: met(0.5) } });
  const a = mk("A", { induces: { CYP3A: { u: 1, source: "virtual" } } });
  near(core.concentrationRatio(b, [a]).r, 0.6667);
});

test("T5 작용제 c=1 → E = 0.5", () => near(core.targetEffect([1]), 0.5));
test("T6 e=0.4 → c = 0.6667", () => near(core.cFromE(0.4), 0.6667));
test("T7 e=0.4, r=1.7241 → E = 0.5348", () => near(core.targetEffect([core.cFromE(0.4) * 1.7241]), 0.5348));
test("T8 같은 대상 e=0.3, e=0.4 → E = 0.5227",
  () => near(core.targetEffect([core.cFromE(0.3), core.cFromE(0.4)]), 0.5227));
test("T8b 두 번째 약 r = 1/(1−0.42) → E = 0.6121",
  () => near(core.targetEffect([core.cFromE(0.3), core.cFromE(0.4) / (1 - 0.42)]), 0.6121));

test("T9 차단제: (1, 1) → 0.3333, (3, 1) → 0.6", () => {
  near(core.targetEffect([1], [1]), 0.3333);
  near(core.targetEffect([3], [1]), 0.6);
  assert.equal(core.targetEffect([], [1]), 0);
});

test("T10 두 대상 c=0.25에서 k=0, 1, 4, 8", () => {
  const e = core.eFromC(0.25);
  [[0, 0.3333], [1, 0.36], [4, 0.4286], [8, 0.5]].forEach(([k, want]) => near(core.combine([e, e], k), want));
});

test("T10b 세 대상 c=0.25, k=2 → c_합 = 1.1875, E = 0.5429", () => {
  near(core.combineSum([0.25, 0.25, 0.25], 2), 1.1875);
  near(core.combine(Array(3).fill(core.eFromC(0.25)), 2), 0.5429);
});

test("T11 역산: f=0.7, g=0.5, R=2.46305 → s = 0.6 (다른 근 2.83은 버림)", () => {
  const roots = core.inhibitionRoots(0.7, 0.5, 2.46305).sort((a, b) => a - b);
  near(roots[0], 0.6);
  near(roots[1], 2.8286);
  near(core.invertInhibition(0.7, 0.5, 2.46305), 0.6);
  assert.throws(() => core.invertInhibition(0.5, 0, 10));
});

test("T12 Ki 방식: 농도 = Ki → s = 0.5", () => near(core.sFromKi(3, 3), 0.5));

test("T13 up c=1, down c=0.25 → 효과 = 0.3",
  () => near(core.effectValue([core.eFromC(1)], [core.eFromC(0.25)], 1), 0.3));

test("T14 s=0.6, dose_ratio=2 → s = 0.75", () => near(core.scaleInhibition(0.6, 2), 0.75));

test("T15 F=0.5, dose=100, CL=10, tau=12, EC50=0.41667 → C = 0.4167, c = 1", () => {
  near(core.pkConcentration(0.5, 100, 10, 12), 0.4167);
  near(core.cFromPk(0.5, 100, 10, 12, 0.41667), 1);
  const d = core.parseDrug({ name: "X", actions: { P: { type: "agonist", F: 0.5, dose: 100, CL: 10, tau: 12,
    EC50: 0.41667, source: "v" } } }, ENZYMES);
  near(d.actions.P.input.C, 0.4167);
  near(d.actions.P.c, 1);
});

const effect = (res, name) => res.effects.find((e) => e.effect === name);
const parse = (raw) => core.parseDrug(raw, ENZYMES);

test("E2E-1 효소 억제로 증강(원인 r)", () => {
  const a = parse({ name: "A", inhibits: { CYP3A: { s: 0.6, t: 0, source: "virtual" } },
    actions: { P: { type: "agonist", e: 0.3, source: "virtual" } } });
  const b = parse({ name: "B", metabolism: { CYP3A: { f: 0.7, g: 0, source: "virtual" } },
    actions: { P: { type: "agonist", e: 0.4, source: "virtual" } } });
  const rules = core.parseRules({ effects: { X: { up: ["P"], source: "virtual" } } });
  const res = core.analyze([a, b], rules, CONFIG);
  near(res.ratios.B.r, 1.7241);
  near(res.ratios.A.r, 1);
  const x = effect(res, "X");
  near(x.B0, 0.5227);
  near(x.Bfull, 0.6121);
  near(x.R, 1.171);
  assert.equal(x.verdict, "증강");
  assert.equal(x.cause, "r");
});

test("E2E-2 대상 시너지로 증강(원인 k)", () => {
  const a = parse({ name: "A", actions: { P: { type: "agonist", c: 0.25, source: "virtual" } } });
  const b = parse({ name: "B", actions: { Q: { type: "agonist", c: 0.25, source: "virtual" } } });
  const rules = core.parseRules({ effects: { Y: { up: ["P", "Q"], k: 4, source: "virtual" } } });
  const y = effect(core.analyze([a, b], rules, CONFIG), "Y");
  near(y.B0, 0.36);
  near(y.Bfull, 0.4286);
  near(y.R, 1.190);
  assert.equal(y.verdict, "증강");
  assert.equal(y.cause, "k");
});

test("E2E-3 같은 효소를 억제하는 약 두 개", () => {
  const a = parse({ name: "A", inhibits: { CYP3A: { s: 0.5, t: 0, source: "virtual" } } });
  const b = parse({ name: "B", inhibits: { CYP3A: { s: 0.5, t: 0, source: "virtual" } } });
  const c = parse({ name: "C", metabolism: { CYP3A: { f: 0.8, g: 0, source: "virtual" } } });
  const rules = core.parseRules({ effects: { X: { up: ["P"], source: "virtual" } } });
  const res = core.analyze([a, b, c], rules, CONFIG);
  near(res.ratios.C.r, 2.5);
  near(res.ratios.A.r, 1);
  near(res.ratios.B.r, 1);
});

test("숫자 표시가 파이썬과 같다", () => {
  const cases = [[1.7241379, "1.724"], [0.52272727, "0.5227"], [100, "100"], [0.05, "0.05"], [1e-17, "1e-17"],
    [12345, "1.234e+04"], [1.0625, "1.062"], [9.99996, "10"], [-0.0857, "-0.0857"], [2, "2"]];
  for (const [x, want] of cases) assert.equal(core.fmtG(x, 4), want);
  assert.equal(core.fmtFixed(0.125, 2), "0.12");
  assert.equal(core.fmtFixed(-0.00001, 4), "-0.0000");
  assert.equal(core.fmtFixed(2.8736, 4), "2.8736");
  assert.equal(core.traceNum(-1), "−1");
});

test("붙여 넣은 글에서 약물 집합 JSON을 꺼낸다", () => {
  const text = "설명 문장\n```json\n{\"drugs\": [], \"rules\": {\"effects\": {}}}\n```\n빠진 값: 없음";
  assert.deepEqual(core.extractJson(text), { drugs: [], rules: { effects: {} } });
  assert.throws(() => core.extractJson("JSON 없음"), core.DataError);
});

// ---------------------------------------------------------------- 데이터가 없을 때
const emptySet = {
  drugs: [
    { name: "약1", metabolism: {}, inhibits: {}, induces: {}, actions: {} },
    { name: "약2", metabolism: {}, inhibits: {}, induces: {}, actions: {} },
    { name: "약3", metabolism: {}, inhibits: {}, induces: {}, actions: {} },
  ],
  rules: { effects: {} },
  missing: [{ drug: "약1", item: "metabolism", reason: "허가사항에 비율 없음" }, "약2 actions"],
};

test("값이 모두 비어 있으면 '데이터가 없어서 계산하지 못했다'", () => {
  const set = core.parseSet(emptySet, ENZYMES);
  assert.equal(set.missing.length, 2);
  assert.deepEqual(set.missing[1], { drug: "", item: "약2 actions", reason: "" });
  const a = core.assessData(set.drugs, set.rules);
  assert.equal(a.overall, "nodata");
  assert.equal(a.conc.status, "nodata");
  assert.equal(a.effect.status, "nodata");
  assert.ok(a.conc.text.startsWith(core.NO_DATA));
  assert.ok(a.effect.text.includes("규칙표(rules)에 효과가 없다"));
  assert.deepEqual(a.values, { cited: 0, assumed: 0, empty: 0 });
});

test("작용 자료만 있으면 (가)만 데이터 없음", () => {
  const a = parse({ name: "A", actions: { P: { type: "agonist", c: 0.25, source: "논문 1" } } });
  const b = parse({ name: "B", actions: { Q: { type: "agonist", c: 0.25, source: "virtual" } } });
  const rules = core.parseRules({ effects: { Y: { up: ["P", "Q"], k: 4, source: "가정: 근거 없음" } } });
  const res = core.assessData([a, b], rules);
  assert.equal(res.overall, "partial");
  assert.equal(res.conc.status, "nodata");
  assert.equal(res.effect.status, "ok");
  assert.deepEqual(res.values, { cited: 1, assumed: 2, empty: 0 });
});

test("효소 자료가 있지만 겹치지 않으면 '계산했다: 변화 없음'", () => {
  const a = parse({ name: "A", inhibits: { CYP2D6: { s: 0.5, t: 0, source: "x" } } });
  const b = parse({ name: "B", metabolism: { CYP3A: { f: 0.7, g: 0, source: "x" } } });
  const res = core.assessData([a, b], core.parseRules({ effects: {} }));
  assert.equal(res.conc.status, "none");
  assert.equal(res.effect.status, "nodata");
  assert.deepEqual(res.noMetabolism, ["A"]);
});

test("억제제와 기질이 같은 약 하나뿐이면 (가)는 데이터 없음", () => {
  const a = parse({ name: "A", metabolism: { CYP3A: { f: 0.5, g: 0, source: "x" } }, inhibits: { CYP3A: { s: 0.5, t: 0, source: "x" } } });
  const b = parse({ name: "B" });
  const res = core.assessData([a, b], core.parseRules({ effects: {} }));
  assert.equal(res.conc.status, "nodata");
});

test("E2E-1 입력은 자료가 충분하다", () => {
  const a = parse({ name: "A", inhibits: { CYP3A: { s: 0.6, t: 0, source: "virtual" } },
    actions: { P: { type: "agonist", e: 0.3, source: "virtual" } } });
  const b = parse({ name: "B", metabolism: { CYP3A: { f: 0.7, g: 0, source: "virtual" } },
    actions: { P: { type: "agonist", e: 0.4, source: "virtual" } } });
  const res = core.assessData([a, b], core.parseRules({ effects: { X: { up: ["P"], source: "virtual" } } }));
  assert.equal(res.overall, "ok");
  assert.deepEqual(res.noMetabolism, ["A"]);
});

test("앱 설치용 파일이 모두 있다", async () => {
  const { readFile, access } = await import("node:fs/promises");
  const root = new URL("../docs/", import.meta.url);
  const sw = await readFile(new URL("sw.js", root), "utf8");
  const files = JSON.parse(`[${sw.match(/const FILES = \[([\s\S]*?)\];/)[1].trim().replace(/,\s*$/, "")}]`);
  for (const f of files) if (f !== "./") await access(new URL(f, root));
  const manifest = JSON.parse(await readFile(new URL("manifest.webmanifest", root), "utf8"));
  for (const icon of manifest.icons) await access(new URL(icon.src, root));
  assert.equal(manifest.display, "standalone");
});
