// AI에 붙여 넣을 프롬프트 두 개. 앱은 AI를 직접 부르지 않는다(사용자가 복사해서 AI에 붙여 넣는다).
import { DISCLAIMER } from "./core.js";
import { CONFIG, ENZYMES } from "./data.js";

const j = CONFIG.judgement;
const flag = CONFIG.flag;

export const RESULT_SLOT = "{{계산 결과}}";
const NAMES_SLOT = "{{약 이름}}";

// 약 이름 입력 칸의 글을 약 이름 목록으로 나눈다(쉼표, 줄바꿈, 세미콜론, 가운뎃점).
export function parseNames(text) {
  const seen = new Set();
  const out = [];
  for (const part of String(text).split(/[,，;\n、·]+/)) {
    const name = part.trim().replace(/^[-•*\d.)\s]+/, "").trim();
    if (name && !seen.has(name)) { seen.add(name); out.push(name); }
  }
  return out;
}

// AI가 찾아볼 자료 출처(공신력 있는 곳만). 위에서부터 먼저 찾는다.
export const SOURCES = [
  { name: "DailyMed (미국 국립의학도서관, 의약품 허가 라벨)", url: "https://dailymed.nlm.nih.gov",
    find: "12.3 Pharmacokinetics(대사 효소, 대사 비율), 7 Drug Interactions(AUC 비), 2 Dosage(권장 용량)" },
  { name: "FDA 약물상호작용 표 (CYP 기질·억제제·유도제 예시)", url: "https://www.fda.gov/drugs/drug-interactions-labeling/healthcare-professionals-fdas-examples-drugs-interact-cyp-enzymes-and-transporter-systems",
    find: "민감 기질, 강한·중간·약한 억제제와 유도제 분류" },
  { name: "Drugs@FDA (FDA 허가 문서)", url: "https://www.accessdata.fda.gov/scripts/cder/daf/",
    find: "허가 라벨 원문, 임상약리 검토서(Clinical Pharmacology Review)의 상호작용 시험 결과" },
  { name: "의약품안전나라 (식품의약품안전처)", url: "https://nedrug.mfds.go.kr",
    find: "국내 허가사항, 성인 1회 권장 용량과 복용 간격, 상품명의 주성분" },
  { name: "약학정보원", url: "https://www.health.kr",
    find: "국내 의약품 정보, 주성분, 용법·용량" },
  { name: "Flockhart 표 (인디애나 대학교 CYP 상호작용 표)", url: "https://drug-interactions.medicine.iu.edu",
    find: "어떤 약이 어떤 CYP의 기질·억제제·유도제인지, 억제의 강도" },
  { name: "DrugBank", url: "https://go.drugbank.com",
    find: "대사 효소, 작용 대상(표적), 억제 상수 Ki" },
  { name: "IUPHAR/BPS Guide to Pharmacology", url: "https://www.guidetopharmacology.org",
    find: "작용 대상(수용체)에 대한 Ki, EC50, IC50" },
  { name: "PubMed (논문 검색)", url: "https://pubmed.ncbi.nlm.nih.gov",
    find: "약물상호작용 임상 시험의 AUC 비, 대사 비율(fm) 논문" },
  { name: "EMA 의약품 정보 (유럽 허가 문서, SmPC)", url: "https://www.ema.europa.eu/en/medicines",
    find: "5.2 Pharmacokinetic properties, 4.5 Interaction" },
];

const sourcesText = () => SOURCES.map((x, i) => `${i + 1}. ${x.name} — ${x.url}\n   찾을 것: ${x.find}`).join("\n");

const STRICT_RULES = `[값의 세 종류]
- 실측값: 위 [자료 출처]에서 확인한 숫자. source에 문서 이름, 항목 번호나 표, 링크를 적는다.
- 가정값: 탐구를 위해 정한 숫자. 사용자가 가정값을 쓰라고 했을 때만 넣고, source에 "virtual" 또는 "가정: 이유"라고 적는다.
- 미확인값: 근거를 찾지 못한 숫자. 넣지 말고 "missing"에 적는다.

[반드시 지킬 것]
1. 숫자를 지어내지 마라. 실측값만 넣고, 출처를 찾지 못한 값은 그 원소를 통째로 빼고 "missing"에 적어라.
2. 값을 하나도 찾지 못해도 괜찮다. 그때는 metabolism, inhibits, induces, actions를 비워 두고 "missing"에 무엇이 없는지 적어라. 계산기가 "데이터가 없어서 계산하지 못했다"고 알려 준다.
3. 이 계산기의 f, g, s, t, c는 허가사항에 그대로 나오지 않는 경우가 많다. 그대로 대응되는 값(예: 라벨의 "fraction metabolized by CYP3A" → f)과 아래 [바로 바꿀 수 있는 식]으로 계산되는 값만 쓰고, 그 밖에 추정이 필요한 값은 넣지 말고 "missing"에 근거 자료(예: "보고된 AUC 비 3.1배, 출처")를 적어라.`;

const GUESS_RULES = `[추측 모드: 켜짐]
정확한 숫자가 없으면, [자료 출처]의 설명 글(예: "주로 CYP3A4로 대사된다", "강한 CYP3A 억제제")을 근거로 아래 [추정 기준표]에 따라 값을 추정해서 넣는다.

[값의 네 종류]
- 실측값: 위 [자료 출처]에서 확인한 숫자. source에 문서 이름, 항목 번호나 표, 링크를 적는다.
- 추정값: 설명 글을 근거로 [추정 기준표]에 따라 정한 숫자. source를 반드시 "추정: "으로 시작하고, 근거 문장(가능하면 원문 그대로)과 출처, 쓴 기준을 적는다.
  예: "추정: DailyMed 12.3 'primarily metabolized by CYP3A4' → 기준표 '주로' f = 0.8"
- 가정값: 사용자가 정해 준 숫자. source에 "virtual" 또는 "가정: 이유".
- 미확인값: 설명 글조차 없는 값. 넣지 말고 "missing"에 적는다.

[반드시 지킬 것]
1. 실측값이 있으면 실측값을 쓰고, 없을 때만 추정한다. 근거 문장이 없는데 추정하지 마라(그건 지어내기다).
2. 추정은 아래 기준표의 값만 쓴다. 기준표에 없는 상황이면 추정하지 말고 "missing"에 적는다.
3. 추정값도 "missing"에 "추정함: 무엇을, 왜"라고 한 줄씩 남긴다.

[추정 기준표]
- f (간의 그 효소가 맡는 비율): 근거 문장 "거의 전부/대부분(almost exclusively, predominantly)" → 0.9, "주로(primarily, mainly, major)" → 0.8, "상당 부분/여러 경로 중 하나(significant, partly)" → 0.5, "일부/소량(minor, to a lesser extent)" → 0.2.
  강한 억제제와 함께 먹었을 때 AUC 비 X가 보고되어 있으면 f = 1 − 1/X 로 계산한다(실측 기반이므로 source에 계산식을 적는다).
- g (장에서 분해되는 비율): CYP3A이고 "장(소장)에서의 대사, 초회 통과 효과가 크다"는 근거가 있을 때만 0.4, 그 밖에는 0.
- s, t (억제 정도, t는 근거 없으면 s와 같게): FDA·Flockhart의 "강한(strong) 억제제" → 0.85, "중간(moderate)" → 0.65, "약한(weak)" → 0.35.
- u (유도): "강한(strong) 유도제" → 4, "중간(moderate)" → 1.5, "약한(weak)" → 0.5.
- e (작용제의 효과 크기, 작용 대상의 c 대신 사용): 권장 용량에서 그 약의 주된 작용(허가 효능) → 0.5, 흔한 부작용으로 나타나는 작용 → 0.2, 드문 부작용 수준 → 0.05.
- c (차단제의 작용 세기): 주된 작용 → 1, 흔한 부작용 수준 → 0.25.
- rules: 효과의 up·down은 약리 설명 글에 맞게 연결하고, k = 1, threshold = null로 둔다.`;

const MAKE_HEAD = `너는 고등학생 수학 탐구용 '약물 상호작용 계산기'에 넣을 입력(약물 집합)을 만드는 도우미다.
이 계산기는 수학 모델이며 실제 복약 판단에 쓰지 않는다.

[조사할 약]
${NAMES_SLOT}

[용량 기준]
- 약 이름 옆에 용량이 적혀 있지 않으면, 그 약의 허가사항(라벨)에 있는 성인 1회 권장 용량과 권장 복용 간격으로 먹는다고 본다. 이 용량이 dose_ratio = 1이다.
- 약 이름 옆에 용량이 적혀 있으면 그 용량을 기준으로 한다.
- 기준으로 삼은 용량과 그 출처를 "dose_basis"에 약마다 적는다.
- 상품명이면 주성분 이름을 함께 적는다(예: "타이레놀(아세트아미노펜)").

[자료 출처] 아래 공신력 있는 곳에서 먼저 찾는다. 웹 검색을 쓸 수 있으면 직접 찾아 확인하고, 다른 곳의 숫자를 쓸 때는 그 문서를 source에 적는다.
${sourcesText()}

[바로 바꿀 수 있는 식] (확인된 숫자에서 계산한 값은 실측값으로 보고, source에 식을 함께 적는다)
- 강한 억제제와 함께 먹었을 때 기질의 AUC 비 X → 그 효소의 f ≈ 1 − 1/X
- 억제제의 Ki와 혈중 농도 → s, t 대신 Ki, conc_liver, conc_gut로 적는다
- 작용 대상의 EC50(또는 KB)과 평균 혈중 농도 → c = 평균 농도 ÷ EC50 (또는 F, dose, CL, tau와 EC50을 그대로 적는다)

[출력]
아래 [형식]의 JSON 하나를 \`\`\`json 코드 블록 안에 출력하라. 찾지 못한 값은 JSON 안의 "missing" 목록에 적는다.
`;

const MAKE_TAIL = `
[모든 경우에 지킬 것]
- 약이 여러 개라고 상호작용이 저절로 생기지 않는다. 한 약이 어떤 효소로 분해되고, 다른 약이 그 효소를 억제·유도한다는 자료가 둘 다 있어야 평균 농도 변화를 계산할 수 있다.
- 효소 이름은 ${ENZYMES.join(", ")} 중에서만 쓴다(예: CYP3A4·CYP3A5는 CYP3A로 적는다).
- 값이 0인 원소는 적지 않는다. 숫자는 따옴표 없이 숫자로 적는다.
- drugs의 actions에 쓴 대상 이름과 rules의 up·down에 쓴 대상 이름은 글자까지 똑같아야 한다.
- 효과(rules)의 up·down 대상은 실제 약리 작용에 맞게 연결하고 source를 적는다. k, threshold는 근거가 없으면 1, null로 둔다.
- JSON 안에는 주석을 넣지 않는다.

[형식]
{
  "drugs": [
    {
      "name": "약 이름",
      "dose_ratio": 1,
      "metabolism": { "효소": { "f": 숫자, "g": 숫자, "source": "출처" } },
      "inhibits":   { "효소": { "s": 숫자, "t": 숫자, "source": "출처" } },
      "induces":    { "효소": { "u": 숫자, "source": "출처" } },
      "actions":    { "대상": { "type": "agonist 또는 antagonist", "c": 숫자, "source": "출처" } }
    }
  ],
  "rules": {
    "effects": {
      "효과 이름": { "up": ["대상"], "down": [], "k": 1, "threshold": null, "source": "출처" }
    }
  },
  "dose_basis": [
    { "drug": "약 이름", "dose": "성인 1회 ○ mg, ○시간마다", "source": "허가사항 등 출처" }
  ],
  "missing": [
    { "drug": "약 이름", "item": "metabolism.CYP3A의 f", "reason": "허가사항에 비율이 없음" }
  ]
}

[값의 뜻]
- metabolism(분해 효소): f = 몸에서 약이 없어지는 전체 중 간의 그 효소가 맡는 비율(0~1), g = 장을 지나면서 그 효소에 분해되는 비율(0~1). 한 약의 f 합 ≤ 1, g 합 ≤ 1.
- inhibits(억제 효소): s = 간에서 막는 정도, t = 장에서 막는 정도(0 ≤ s, t < 1). s, t 대신 Ki와 conc_liver, conc_gut(같은 단위)를 적어도 된다. 그러면 계산기가 x = 농도 ÷ Ki, s = x ÷ (1 + x)로 바꾼다.
- induces(유도 효소): u = 효소 작용이 (1 + u)배가 된다는 뜻(u ≥ 0).
- actions(작용 대상): type은 "agonist"(작용제) 또는 "antagonist"(차단제). c = 기준 용량에서 평균 농도 ÷ 반작용 농도.
  c 대신 e(기준 용량에서의 효과 크기 0~1, 작용제만), 또는 F, dose, CL, tau와 EC50(작용제)·KB(차단제)를 적어도 된다(C = F × dose ÷ (CL × tau), 단위를 서로 맞출 것).
- dose_ratio: 기준 용량의 몇 배를 먹는지(권장 용량이면 1).
- rules.effects: 효과마다 그 효과를 올리는 대상(up), 내리는 대상(down), 대상끼리의 관계 k(0 = 같은 대상처럼 더함, 1 = 서로 따로 작용, 1보다 크면 서로 도움, 0~1이면 일부 겹침, 근거가 없으면 1), 발현 기준 threshold(근거가 없으면 null).
`;

// 약 이름을 넣은 입력 만들기 프롬프트. guess = true면 추측 모드(설명 글로 값 추정).
export function makePrompt(names = [], { guess = false } = {}) {
  const list = names.length
    ? names.map((n) => `- ${n}`).join("\n")
    : "- (여기에 약 이름을 한 줄에 하나씩 적는다. 용량은 안 적어도 된다)";
  return `${MAKE_HEAD.replace(NAMES_SLOT, list)}\n${guess ? GUESS_RULES : STRICT_RULES}\n${MAKE_TAIL}`;
}

export const MAKE_PROMPT = makePrompt();
export const MAKE_PROMPT_GUESS = makePrompt([], { guess: true });

export const READ_PROMPT = `아래 [계산 결과]는 고등학생 수학 탐구용 '약물 상호작용 계산기'가 낸 값이다. 이것을 해석해 줘.

[출력 형식] — 아래 세 부분만, 이 순서와 제목 그대로 출력한다. 인사말, 규칙을 되풀이하는 말, 용어 목록, 입력 JSON이나 계산 과정 옮겨 적기, 그 밖의 다른 내용은 출력하지 않는다.

## 1. 전문 해석
- 약리학·수학 용어를 써서 정확하게, 항목마다 한 줄씩 쓴다. 10줄 이내.
- 넣을 것: 평균 농도가 바뀐 약(겹친 효소, 억제·유도, r 값) / 효과마다 판정과 R(또는 d), 원인(r 기여, k 기여) / 발현 여부 / 결과를 좌우한 추정값·가정값.
- 바뀐 것이 없는 약·효과는 하나로 묶어 "변화 없음"이라고만 쓴다.

## 2. 일반인용 해설
- 약을 전혀 모르는 사람도 읽을 수 있게, 중학생이 아는 말로 3~5문장 쓴다.
- r, B₀, B_full, R, k, CYP, 판정 같은 기호와 전문 용어는 쓰지 않는다. 꼭 필요하면 "몸에서 약을 분해하는 효소"처럼 풀어 쓴다.
- 숫자는 꼭 필요한 것만 "약 2배"처럼 반올림해서 쓴다.
- 예: "A약이 B약을 분해하는 효소를 막아서, B약이 몸속에 약 3배 더 오래 많이 남는 것으로 계산됐어요. 그래서 B약의 졸린 효과가 혼자 먹을 때보다 세지는 것으로 나왔어요."

## 3. 최종 요약
- 한 문장으로 결론만 쓴다.
- 그 아래 줄에 "실제로 약을 먹을지·바꿀지는 의사·약사와 상의하세요."
- 마지막 줄에 "${DISCLAIMER}"

[지킬 것]
- [계산 결과]에 있는 숫자와 판정만 쓴다. 새 숫자를 만들거나 다시 계산하지 않고, 계산 결과에 없는 약의 일반 상식을 덧붙이지 않는다.
- 약을 먹어라·끊어라·용량을 바꿔라 같은 복약 조언은 하지 않는다(3번의 상의 안내 한 줄만).
- [데이터 상태]에 "데이터가 없어서 계산하지 못했다"인 부분은 세 부분 모두에서 "데이터가 없어 계산하지 못함"이라고만 쓰고 추측으로 채우지 않는다. 전문 해석에는 계산하려면 무엇이 필요한지 한 줄로 적는다.
- source가 "추정"으로 시작하는 값은 설명 글로 어림한 값, "virtual"·"가정"은 연습용 값, 빈칸은 출처 없음이다. 결과가 이런 값에 기대고 있으면 전문 해석에 한 줄, 일반인용 해설에 "정확한 자료가 아니라 어림한 값으로 계산했다"는 뜻을 한 번 적는다.

[판정을 읽는 법] (해석에 참고만 하고 출력하지 않는다)
- r: 함께 먹을 때 그 약의 평균 혈중 농도가 몇 배인지. r ≥ ${flag.r_high} 또는 r ≤ ${flag.r_low}이면 크게 바뀐 것.
- B₀: 상호작용이 없다고 볼 때의 예상 효과, B_r: 농도 변화만 반영, B_full: 함께 먹을 때 계산된 효과.
- 판정: R = B_full ÷ B₀가 ${j.ratio_up}보다 크면 증강(세짐), ${j.ratio_down}보다 작으면 감소(약해짐), 그 사이면 독립(거의 그대로). |B₀| < ${j.b0_small}이면 차이 d로 본다(|d| < ${j.diff_small}이면 독립).
- 원인: r = 혈중 농도가 바뀌어서, k = 작용끼리 서로 돕거나 겹쳐서. 발현: 약 하나씩은 기준 미만인데 함께 먹으면 기준 이상.

[계산 결과]
${RESULT_SLOT}
`;
