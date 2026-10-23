// 화면 처리. 계산은 모두 core.js(파이썬과 같은 식)로 하고, summary.js는 결과를 쉬운 말로 바꾸기만 한다.
import * as core from "./core.js";
import { CONFIG, DEMO_SET, ENZYMES } from "./data.js";
import { MAKE_PROMPT, READ_PROMPT, RESULT_SLOT, makePrompt, parseNames } from "./prompts.js";
import { buildSummary, CAUSE_PLAIN, VERDICT_PLAIN, VERDICT_TONE } from "./summary.js";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const STORE_INPUT = "dic.input.v1";
const STORE_NAMES = "dic.names.v1";
const TABS = ["calc", "rules", "tutorial", "install"];

const state = {
  raw: null,        // 붙여 넣은 JSON
  set: null,        // 검사한 약물 집합 {drugs, rules, warnings, usedFallback, missing, doseBasis}
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
  toastTimer = setTimeout(() => el.classList.remove("show"), 2400);
}

async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text);
    toast(`${label} 복사했어요`);
    return true;
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
  return ok;
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

// ---------------------------------------------------------------- 탭과 단계 표시

function showTab(name) {
  if (name === "prompts") name = "tutorial";   // 예전 주소(#prompts)
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

function updateStepper() {
  const names = parseNames($("#names").value);
  const hasInput = $("#input").value.trim().length > 0;
  const hasResult = !!state.result;
  const done = { 1: names.length > 0 || hasInput || hasResult, 2: hasResult, 3: hasResult };
  const now = hasResult ? 3 : (hasInput || names.length ? 2 : 1);
  $$(".stepper li").forEach((li) => {
    const k = Number(li.dataset.step);
    li.classList.toggle("done", done[k] && k !== now);
    li.classList.toggle("now", k === now);
  });
}

// ---------------------------------------------------------------- 1. 약 이름

function renderNames() {
  const names = parseNames($("#names").value);
  storeSet(STORE_NAMES, $("#names").value);
  $("#name-chips").innerHTML = names.map((n, i) => `<span class="pill"><span class="cap"></span><span class="label">${esc(n)}</span>`
    + `<button type="button" data-remove="${i}" aria-label="${esc(n)} 빼기">×</button></span>`).join("");
  $("#copy-make").disabled = names.length === 0;
  $("#copy-make").textContent = names.length ? `AI에게 물어볼 글 복사 (약 ${names.length}개)` : "AI에게 물어볼 글 복사";
  $("#make-preview").value = makePrompt(names);
  updateStepper();
}

function removeName(index) {
  const names = parseNames($("#names").value);
  names.splice(index, 1);
  $("#names").value = names.join(", ");
  renderNames();
}

// ---------------------------------------------------------------- 2. 붙여 넣기와 계산

function showMessages(errors, warnings) {
  const parts = [];
  if (errors.length) {
    parts.push(`<div class="msg err"><b>입력 오류</b><ul>${errors.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>
      <p class="hint">이 오류 문장을 AI에게 보여 주고 "JSON을 고쳐 줘"라고 하면 돼요.</p></div>`);
  }
  if (warnings.length) {
    const list = `<ul>${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>`;
    parts.push(`<details class="msg warn"><summary>확인할 점 ${warnings.length}개 (계산은 됐어요)</summary>${list}</details>`);
  }
  $("#messages").innerHTML = parts.join("");
}

function hideResult() {
  state.result = null;
  $("#result-card").hidden = true;
  updateStepper();
}

function readInput({ quiet = false } = {}) {
  const text = $("#input").value;
  storeSet(STORE_INPUT, text);
  if (!text.trim()) {
    state.set = null;
    hideResult();
    if (!quiet) showMessages(["붙여 넣은 글이 없어요. AI 답을 붙여 넣거나 「예시로 바로 해 보기」를 눌러 보세요"], []);
    renderRules();
    return;
  }
  try {
    state.raw = core.extractJson(text);
    state.set = core.parseSet(state.raw, ENZYMES, DEMO_SET.rules);
  } catch (err) {
    state.set = null;
    hideResult();
    showMessages([err.message], []);
    renderRules();
    return;
  }
  state.selected = new Set(state.set.drugs.map((d) => d.name));
  renderPick();
  renderRules();
  compute();
  if (!quiet) $("#result-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderPick() {
  $("#pick").innerHTML = state.set.drugs.map((d, i) => `
    <label><input type="checkbox" data-i="${i}" ${state.selected.has(d.name) ? "checked" : ""}>${esc(d.name)}</label>`).join("");
}

function compute() {
  const set = state.set;
  state.drugs = set.drugs.filter((d) => state.selected.has(d.name));
  const warnings = [...set.warnings];
  $("#result-card").hidden = false;
  if (state.drugs.length < 2) {
    $("#pick-msg").textContent = set.drugs.length < 2
      ? "약이 1개뿐이에요. 상호작용은 약이 2개 이상일 때 계산해요."
      : "함께 먹을 약을 2개 이상 골라 주세요.";
    state.result = null;
    $("#result").innerHTML = "";
    $("#detail-box").hidden = true;
    $("#trace-box").hidden = true;
    $(".actions").hidden = true;
    showMessages([], warnings);
    updateStepper();
    return;
  }
  $("#pick-msg").textContent = "";
  try {
    state.result = core.analyze(state.drugs, set.rules, CONFIG, warnings);
    [state.trace] = core.buildTrace(state.drugs, set.rules, CONFIG, state.result);
    state.assess = core.assessData(state.drugs, set.rules);
  } catch (err) {
    showMessages([`계산 중 오류: ${err.message}`], warnings);
    hideResult();
    return;
  }
  showMessages([], warnings);
  $(".actions").hidden = false;
  renderResult();
  updateStepper();
}

// ---------------------------------------------------------------- 3. 결과

const STATUS_CLASS = { ok: "ok", none: "ok", nodata: "nodata" };
const HEAD_ICON = { alert: "⚠️", calm: "✅", partial: "◐", nodata: "⛔" };

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
  const { missing, doseBasis } = state.set;
  const doseHtml = doseBasis.length
    ? `<details><summary>기준 용량 ${doseBasis.length}개</summary><ul>${doseBasis.map((d) =>
      `<li><b>${esc(d.drug)}</b> ${esc(d.dose)}${d.source ? ` <span class="muted">(${esc(d.source)})</span>` : ""}</li>`).join("")}</ul></details>`
    : '<p class="muted">기준 용량: 따로 적힌 것이 없어 허가사항의 성인 권장 용량(dose_ratio = 1)으로 봐요.</p>';
  const missingHtml = missing.length
    ? `<details><summary>AI가 찾지 못한 값 ${missing.length}개</summary><ul>${missing.map((m) =>
      `<li>${esc([m.drug, m.item].filter(Boolean).join(" · "))}${m.reason ? ` <span class="muted">(${esc(m.reason)})</span>` : ""}</li>`).join("")}</ul></details>`
    : "";
  const body = `<div class="status ${a.overall}">
    <p class="status-head">${head}</p>
    <ul class="status-list">${line("혈중 농도 변화", a.conc)}${line("효과의 겹침", a.effect)}</ul>
    <p class="muted">${esc(valueLine)}</p>
    ${doseHtml}${missingHtml}
  </div>`;
  // 문제가 없으면 접어 두고, 데이터가 없을 때만 펼쳐서 보여 준다
  return a.overall === "ok"
    ? `<details class="plain status-wrap"><summary>데이터 상태: 계산에 필요한 자료가 있어요</summary>${body}</details>`
    : body;
}

function coverageTable(a) {
  const cell = (n) => (n ? `${n}개` : '<span class="none">없음</span>');
  return table(["약", "분해 효소", "억제", "유도", "작용 대상", "규칙표와 연결"], a.perDrug.map((p) => [
    esc(p.name), cell(p.metabolism), cell(p.inhibits), cell(p.induces), cell(p.actions), cell(p.linked)]));
}

// 막대 길이: r은 1배를 가운데로 0~4배, 효과는 0~1
const meterR = (r) => Math.max(4, Math.min(100, (Math.log2(Math.max(r, 1e-6)) + 2) / 4 * 100));
const meterE = (x) => Math.max(2, Math.min(100, Math.abs(x) * 100));

function renderResult() {
  const res = state.result;
  const a = state.assess;
  const sum = buildSummary(res, a, CONFIG);
  const out = [];
  const h = sum.headline;
  out.push(`<div class="headline ${h.tone}"><span class="icon" aria-hidden="true">${HEAD_ICON[h.tone]}</span>
    <div><h3>${esc(h.title)}</h3><p>${esc(h.text)}</p></div></div>`);
  out.push(dataStatusHtml(a));

  const hasNumbers = a.overall !== "nodata";
  $("#detail-box").hidden = !hasNumbers;
  $("#trace-box").hidden = !hasNumbers;

  if (!hasNumbers) {
    out.push('<p class="section-title">약마다 입력된 자료</p>');
    out.push(coverageTable(a));
    out.push(`<p class="hint">값을 지어내지 않고 계산을 멈췄어요. AI에게 출처가 있는 값을 더 찾아 달라고 하거나,
      연습이라면 source를 "virtual"로 적은 가정값을 넣어 보세요.</p>`);
    $("#result").innerHTML = out.join("");
    $("#detail").innerHTML = "";
    $("#trace").innerHTML = "";
    return;
  }

  out.push('<p class="section-title">💊 혈중 농도 변화</p>');
  if (a.conc.status === "nodata") out.push(`<p class="nodata-line">${esc(a.conc.text)}</p>`);
  else if (!sum.conc.length) out.push('<p class="hint">고른 약끼리 겹치는 분해 효소가 없어 혈중 농도는 그대로예요(×1).</p>');
  else {
    out.push(`<div class="cards">${sum.conc.map((c) => `<div class="icard ${c.tone}">
      <h4>${esc(c.title)} <span class="badge ${c.tone}">${esc(c.badge)}</span></h4>
      <div class="meter" aria-hidden="true"><i style="width:${meterR(c.r)}%"></i></div>
      <p>${esc(c.text)}</p></div>`).join("")}</div>`);
  }

  out.push('<p class="section-title">🎯 효과 변화</p>');
  if (a.effect.status === "nodata") out.push(`<p class="nodata-line">${esc(a.effect.text)}</p>`);
  else if (!sum.effects.length) out.push('<p class="hint">고른 약이 작용하는 효과가 규칙표에 없어요.</p>');
  else {
    out.push(`<div class="cards">${sum.effects.map((e) => {
      const ef = res.effects.find((x) => x.effect === e.effect);
      return `<div class="icard ${e.tone}">
        <h4>${esc(e.effect)} <span class="badge ${e.tone}">${esc(e.plain)}</span></h4>
        <div class="meter" aria-hidden="true"><i style="width:${meterE(ef.Bfull)}%"></i></div>
        <p class="drugs">관련 약: ${esc(e.drugs.join(", "))}</p>
        ${e.lines.map((l) => `<p>${esc(l)}</p>`).join("")}</div>`;
    }).join("")}</div>`);
  }
  if (a.conc.status === "nodata" && a.effect.status !== "nodata") {
    out.push('<p class="hint">혈중 농도 변화는 자료가 없어 반영하지 못했어요(모든 약 ×1로 계산). 그래서 원인으로 「혈중 농도」는 나올 수 없어요.</p>');
  }
  $("#result").innerHTML = out.join("");
  $("#detail").innerHTML = detailHtml(res, a);
  $("#trace").innerHTML = renderMarkdown(state.trace);
}

function detailHtml(res, a) {
  const out = [];
  out.push('<p class="section-title">평균 농도 변화 r</p>');
  if (a.conc.status === "nodata") out.push(`<p class="nodata-line">${esc(a.conc.text)}</p>`);
  else {
    const noMet = new Set(a.noMetabolism);
    out.push(table(["약", "r_간", "r_장", "r", "표시"], res.drugs.map((n) => {
      const v = res.ratios[n];
      if (noMet.has(n)) return [esc(n), "", "", '<span class="none">자료 없음</span>', '<span class="muted">분해 효소 자료 없음</span>'];
      return [esc(n), f4(v.r_liver), f4(v.r_gut), `<b>${f4(v.r)}</b>`,
        v.flag ? `<span class="badge ${v.flag.includes("증가") ? "up" : "down"}">${v.flag}</span>` : ""];
    }), [1, 2, 3]));
  }
  out.push('<p class="section-title">효과별 결과</p>');
  const effects = res.effects.filter((e) => e.involved.length);
  if (a.effect.status === "nodata") out.push(`<p class="nodata-line">${esc(a.effect.text)}</p>`);
  else if (effects.length) {
    out.push(table(["효과", "관련 약", "B₀", "B_r", "B_full", "R 또는 d", "판정", "원인", "발현"], effects.map((e) => {
      const rd = e.R !== null ? `R = ${f4(e.R)}` : `d = ${f4(e.d)}`;
      const shown = e.manifest === null ? "-" : `${e.manifest ? "<b>발현</b>" : "아님"}<br><span class="muted">${esc(e.manifest_kind)}</span>`;
      return [esc(e.effect), esc(e.involved.join(", ")), f4(e.B0), f4(e.Br), `<b>${f4(e.Bfull)}</b>`, rd,
        `<span class="badge ${VERDICT_TONE[e.verdict]}">${e.verdict}</span><br><span class="muted">${VERDICT_PLAIN[e.verdict]}</span>`,
        `<b>${esc(e.cause)}</b><br><span class="muted">${esc(CAUSE_PLAIN[e.cause] || "")}<br>r ${f4(e.r_contrib)} · k ${f4(e.k_contrib)}</span>`, shown];
    }), [2, 3, 4, 5], [1, 6, 7, 8]));
  }
  const cls = res.classification;
  const typeKo = { agonist: "작용제", antagonist: "차단제" };
  out.push('<p class="section-title">이름이 겹친 곳 (분류)</p>');
  out.push(cls.concentration.length
    ? table(["바꾸는 약", "바뀌는 약", "겹친 효소"], cls.concentration.map((c) => [esc(c.from), esc(c.to), esc(c.how.join(", "))]))
    : '<p class="hint">평균 농도를 바꾸는 순서쌍: 없음</p>');
  if (cls.same_target.length) {
    out.push(table(["약 1", "약 2", "같은 대상", "종류"], cls.same_target.map((s) =>
      [esc(s.a), esc(s.b), esc(s.target), `${s.label} (${typeKo[s.types[0]]}·${typeKo[s.types[1]]})`])));
  }
  if (cls.same_effect.length) {
    out.push(table(["약 1", "약 2", "효과", "대상 1", "대상 2", "방향"], cls.same_effect.map((s) =>
      [esc(s.a), esc(s.b), esc(s.effect), esc(`${s.target_a}(${s.dir_a})`), esc(`${s.target_b}(${s.dir_b})`), s.same_dir ? "같은 방향" : "반대 방향"])));
  }
  out.push('<p class="section-title">약마다 입력된 자료</p>');
  out.push(coverageTable(a));
  return out.join("");
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

// ---------------------------------------------------------------- AI 해석용 글

function statusText(a) {
  const v = a.values;
  const lines = [`(가) 평균 농도 변화: ${a.conc.text}`, ...a.conc.notes.map((n) => `  - ${n}`),
    `(나) 작용의 겹침: ${a.effect.text}`, ...a.effect.notes.map((n) => `  - ${n}`),
    `입력된 값: 출처 있음 ${v.cited}개, 가정값(virtual·가정) ${v.assumed}개, 출처 빈칸 ${v.empty}개`];
  const { missing, doseBasis } = state.set;
  lines.push("[용량 기준]");
  if (doseBasis.length) for (const d of doseBasis) lines.push(`  - ${d.drug}: ${d.dose}${d.source ? ` (${d.source})` : ""}`);
  else lines.push("  - 따로 적힌 것이 없어 허가사항의 성인 권장 용량(dose_ratio = 1)으로 봄");
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
  const sum = buildSummary(res, a, CONFIG);
  const plain = [sum.headline.title, ...sum.conc.map((c) => `- ${c.text}`),
    ...sum.effects.map((e) => `- ${e.title}: ${e.lines.join(" / ")}`)];
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
    ...plain,
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
    origin = state.set.usedFallback ? "(AI 답에 rules가 없어 기본 예시 규칙표 사용)" : "(AI 답에 들어 있던 규칙표)";
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
    : '<p class="nodata-line">규칙표에 효과가 없어요. 효과의 겹침은 계산할 수 없어요.</p>';

  const j = CONFIG.judgement;
  $("#config-table").innerHTML = table(["항목", "값", "뜻"], [
    ["비율 판정", `${j.ratio_down} / ${j.ratio_up}`, `|B₀| ≥ ${j.b0_small}이면 R = B_full ÷ B₀. R > ${j.ratio_up} 세짐(증강), R < ${j.ratio_down} 약해짐(감소), 그 사이 거의 그대로(독립)`],
    ["차이 판정", `${j.diff_small}`, `|B₀| < ${j.b0_small}이면 d = (B_full − B₀) × (B₀의 부호). |d| < ${j.diff_small}이면 거의 그대로`],
    ["원인 표시", `${j.cause_min}`, `|r 기여| 또는 |k 기여|가 ${j.cause_min} 이상이면 원인으로 표시`],
    ["혈중 농도 크게 바뀜", `${CONFIG.flag.r_low} / ${CONFIG.flag.r_high}`, `r ≥ ${CONFIG.flag.r_high} 또는 r ≤ ${CONFIG.flag.r_low}이면 크게 바뀐 것으로 표시`],
  ].map(([a, b, c]) => [esc(a), esc(b), `<span class="wrap">${esc(c)}</span>`]));
}

// ---------------------------------------------------------------- 사용법

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
  $("#tut-next").textContent = tutStep === steps.length - 1 ? "시작하러 가기" : "다음";
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
    ratio: `|B₀| ≥ ${j.b0_small}이면 R = B_full ÷ B₀로 보고 R > ${j.ratio_up} 세짐, R < ${j.ratio_down} 약해짐, 그 사이 거의 그대로. `
      + `|B₀|가 더 작으면 d = (B_full − B₀) × (B₀의 부호)로 보고 |d| < ${j.diff_small}이면 거의 그대로`,
    cause: `|기여| ≥ ${j.cause_min}인 것을 원인으로 표시 (r: 혈중 농도가 바뀌어서, k: 작용끼리 돕거나 겹쳐서)`,
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
  $("#names").value = DEMO_SET.drugs.map((d) => d.name).join(", ");
  renderNames();
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

  // 1. 약 이름
  $("#names").addEventListener("input", renderNames);
  $("#name-chips").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-remove]");
    if (b) removeName(Number(b.dataset.remove));
  });
  $("#copy-make").addEventListener("click", async () => {
    const names = parseNames($("#names").value);
    if (await copyText(makePrompt(names), "AI에게 물어볼 글을")) {
      toast("복사했어요. AI 채팅에 붙여 넣고, 받은 답을 2번 칸에 붙여 넣으세요");
    }
  });
  $("#example").addEventListener("click", loadExample);

  // 2. 붙여 넣기
  $("#run").addEventListener("click", () => readInput());
  $("#input").addEventListener("input", updateStepper);
  $("#paste").addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text.trim()) { toast("복사된 글이 없어요"); return; }
      $("#input").value = text;
      readInput();
    } catch {
      toast("붙여넣기를 할 수 없어요. 칸을 길게 눌러 「붙여넣기」를 고르세요");
      $("#input").focus();
    }
  });
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

  // 3. 결과
  $("#pick").addEventListener("change", (ev) => {
    const box = ev.target.closest("input[data-i]");
    if (!box) return;
    const name = state.set.drugs[Number(box.dataset.i)].name;
    if (box.checked) state.selected.add(name); else state.selected.delete(name);
    compute();
  });
  $("#copy-trace").addEventListener("click", () => copyText(state.trace, "계산 과정을"));
  $("#save-trace").addEventListener("click", () => download(`계산과정_${state.drugs.map((d) => d.name).join("+")}.md`, state.trace));
  $("#copy-read").addEventListener("click", async () => {
    if (await copyText(READ_PROMPT.replace(RESULT_SLOT, resultText()), "해석 부탁 글을")) {
      toast("복사했어요. AI 채팅에 붙여 넣으면 결과를 쉬운 말로 설명해 줘요");
    }
  });
  $("#copy-result").addEventListener("click", () => copyText(`${resultText()}\n`, "결과를"));
  $("#print").addEventListener("click", () => {
    $$("#result-card details").forEach((d) => { d.open = true; });
    window.print();
  });

  // 사용법 탭의 프롬프트 원문
  $("#make-prompt").value = MAKE_PROMPT;
  $("#read-prompt").value = READ_PROMPT;
  $("#copy-make-empty").addEventListener("click", () => copyText(MAKE_PROMPT, "입력 만들기 프롬프트를"));
  $("#copy-read-empty").addEventListener("click", () => copyText(READ_PROMPT, "해석 프롬프트를"));

  $("#enzymes").innerHTML = ENZYMES.map((e) => `<span>${esc(e)}</span>`).join("");
  setupTutorial();
  setupInstall();
  renderRules();

  $("#names").value = storeGet(STORE_NAMES) || "";
  renderNames();
  const saved = storeGet(STORE_INPUT);
  if (saved && saved.trim()) {
    $("#input").value = saved;
    readInput({ quiet: true });
  }
  updateStepper();
  showTab(location.hash.slice(1) || "calc");
}

init();
