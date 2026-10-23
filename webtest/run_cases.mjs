// 파이썬과 비교하기 위한 실행기: 표준 입력으로 {config, enzymes, cases:[{id, drugs, rules}]}를 받아
// 각 경우의 검사 결과·계산 결과·계산 과정을 JSON으로 출력한다(tests/test_web.py가 사용).
import * as core from "../docs/core.js";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const { config, enzymes, cases } = JSON.parse(input);

const out = cases.map(({ id, drugs: rawDrugs, rules: rawRules }) => {
  const warnings = [];
  try {
    const drugs = rawDrugs.map((d) => core.parseDrug(d, enzymes, warnings));
    const rules = core.parseRules(rawRules, warnings);
    const result = core.analyze(drugs, rules, config, warnings);
    const [trace] = core.buildTrace(drugs, rules, config, result);
    return { id, drugs, warnings, result, trace };
  } catch (err) {
    return { id, error: err.message, warnings };
  }
});
process.stdout.write(JSON.stringify(out));
