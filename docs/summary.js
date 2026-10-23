// 계산 결과를 쉬운 말로 바꾼다. 계산 식은 core.js 그대로이고, 여기서는 문장만 만든다.
import { fmtFixed, INCREASE, DECREASE, INDEPENDENT } from "./core.js";

export const VERDICT_PLAIN = { [INCREASE]: "세짐", [DECREASE]: "약해짐", [INDEPENDENT]: "거의 그대로" };
export const VERDICT_TONE = { [INCREASE]: "up", [DECREASE]: "down", [INDEPENDENT]: "same" };
export const CAUSE_PLAIN = {
  r: "혈중 농도가 바뀌어서",
  k: "작용끼리 서로 돕거나 겹쳐서",
  "r+k": "혈중 농도 변화와 작용 겹침이 둘 다",
  "없음": "뚜렷한 한 가지 원인 없이",
  "-": "",
};

const f2 = (x) => fmtFixed(x, 2).replace("-", "−");

function ratioText(e) {
  if (e.R === null) return ` (차이 ${f2(e.d)})`;
  if (e.R < 0) return " (효과의 방향이 반대로 바뀜)";
  return ` (${f2(e.R)}배)`;
}

// 약마다 혈중 농도가 얼마나 바뀌는지
function concentrationCards(res, assess, cfg) {
  if (assess.conc.status === "nodata") return [];
  const noMet = new Set(assess.noMetabolism);
  const cards = [];
  for (const name of res.drugs) {
    if (noMet.has(name)) continue;
    const info = res.ratios[name];
    const causes = [];
    for (const [enz, rem] of Object.entries(info.enzymes)) {
      for (const [who] of rem.inhibitors) causes.push(`${enz} 억제(${who})`);
      for (const [who] of rem.inducers) causes.push(`${enz} 유도(${who})`);
    }
    if (!causes.length) continue;
    const r = info.r;
    const big = r >= cfg.flag.r_high || r <= cfg.flag.r_low;
    const dir = r > 1 ? "높아져요" : (r < 1 ? "낮아져요" : "그대로예요");
    cards.push({
      drug: name,
      r,
      tone: big ? (r > 1 ? "up" : "down") : "same",
      big,
      title: `${name} 혈중 농도 ×${f2(r)}`,
      text: `${causes.join(", ")} → ${name}의 평균 농도가 약 ${f2(r)}배로 ${dir}.`,
      badge: big ? (r > 1 ? "크게 높아짐" : "크게 낮아짐") : "조금 바뀜",
    });
  }
  return cards;
}

// 효과마다 세지는지 약해지는지
function effectCards(res, assess) {
  if (assess.effect.status === "nodata") return [];
  return res.effects.filter((e) => e.involved.length).map((e) => {
    const lines = [
      `함께 먹으면 ${f2(e.Bfull)}, 상호작용이 없다고 보면 ${f2(e.B0)}${ratioText(e)}`,
    ];
    if (e.verdict !== INDEPENDENT && CAUSE_PLAIN[e.cause]) lines.push(`원인: ${CAUSE_PLAIN[e.cause]}`);
    if (e.manifest === true) {
      lines.push(`기준값 ${e.rule.threshold}을 넘어요 — ${e.manifest_kind === "상호작용 때문에 발현" ? "따로 먹을 땐 안 넘다가 상호작용 때문에 넘어요" : "효과를 더하기만 해도 넘어요"}`);
    } else if (e.manifest === false && e.manifest_kind.startsWith("단독으로")) {
      lines.push(`기준값 ${e.rule.threshold}: 약 하나만으로도 이미 넘어요`);
    }
    return {
      effect: e.effect,
      verdict: e.verdict,
      tone: VERDICT_TONE[e.verdict],
      plain: VERDICT_PLAIN[e.verdict],
      title: `${e.effect}: ${VERDICT_PLAIN[e.verdict]}`,
      drugs: e.involved,
      lines,
      manifest: e.manifest,
    };
  });
}

export function buildSummary(res, assess, cfg) {
  if (assess.overall === "nodata") {
    return {
      headline: { tone: "nodata", title: "데이터가 없어서 계산하지 못했어요", text: "약 이름만 있고 계산에 필요한 값이 없어요. 아래 데이터 상태를 확인하세요." },
      conc: [], effects: [],
    };
  }
  const conc = concentrationCards(res, assess, cfg);
  const effects = effectCards(res, assess);
  const notable = conc.filter((c) => c.big).length + effects.filter((e) => e.verdict !== INDEPENDENT).length;
  const partial = assess.overall === "partial" ? " 일부는 데이터가 없어 계산하지 못했어요." : "";
  const headline = notable
    ? { tone: "alert", title: `눈여겨볼 상호작용 ${notable}건`, text: `계산한 범위에서 혈중 농도나 효과가 뚜렷하게 바뀌는 곳이에요.${partial}` }
    : { tone: "calm", title: "뚜렷한 상호작용이 보이지 않아요", text: `입력된 자료로 계산한 범위에서는 크게 바뀌는 곳이 없어요.${partial}` };
  if (assess.overall === "partial") headline.tone = notable ? "alert" : "partial";
  return { headline, conc, effects };
}
