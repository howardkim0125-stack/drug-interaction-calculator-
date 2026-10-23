# 약물 상호작용 계산 시스템 (수학 탐구)

> 수학 탐구 모델의 결과이며 실제 복약 판단이 아니다.

## 준비

```
pip install -r requirements.txt
```

## 실행

| 명령 | 하는 일 | 결과 |
|---|---|---|
| `python -m pytest` | 테스트 전체(T1~T15, E2E-1~3, 웹앱 일치 검사 등) | 화면 |
| `python run_demo.py` | 예시 가상 약 4개 함께 계산 | `out/demo_*` |
| `python run_demo.py 가상약A 가상약B` | 고른 약만 계산 | `out/demo_*` |
| `python run_demo.py 가상약A 가상약B --trace` | 계산 과정을 식 순서대로 출력 | `out/demo_trace.md` |
| `python run_demo.py --drugs data/drugs_내약.json --rules data/rules.json --prefix 내약` | 내 자료로 계산 | `out/내약_*` |
| `python run_eval.py` | 가상 약 20개, 2약 조합 전체 + 3약 조합 200개 평가 | `out/eval_*`, `out/run_log.json` |
| `python run_eval.py --no-triples` | 3약 조합 없이 평가 | `out/eval_*` |
| `python run_eval.py --stress` | 스트레스 시험(요인별 세기 0·0.1·0.2·0.4, seed 10개) | `out/stress_*` |
| `python run_eval.py --compare` | 비교 모델 1(단순 합산)·2(비례)와 현재 시스템(seed 10개) | `out/compare_models*` |
| `python run_eval.py --sensitivity` | 판정 비율 기준 1.03/0.97, 1.05/0.95, 1.10/0.90 비교 | `out/sensitivity*` |
| `python run_eval.py --all` | 위 평가 네 가지 모두 | 위 파일 전부 |
| `python figures.py` | 보고서용 그래프 7개(200dpi) | `out/figures/` |
| `python -m real.compare data/내쌍.csv` | 실제 약 쌍 보정·검증 비교 | `out/real_compare.csv` |

## 웹앱 (아이패드·브라우저)

- 주소(GitHub Pages를 켠 뒤): https://howardkim0125-stack.github.io/drug-interaction-calculator-/
- 파일은 `docs/`에 있다. 서버나 AI API 없이 브라우저 안에서만 계산하고, 계산 식은 파이썬과 같다.
- 쓰는 순서: ① 약 이름만 적고 「AI에게 물어볼 글 복사」 → AI 채팅에 붙여 넣기 → ② AI 답을 붙여 넣고 「계산하기」 → ③ 결과.
  용량을 안 적으면 허가사항의 성인 1회 권장 용량을 기준(dose_ratio = 1)으로 삼도록 AI에게 지시한다.
- 결과는 쉬운 말 카드(혈중 농도 ×몇 배, 효과 세짐·약해짐·거의 그대로)로 먼저 보여 주고,
  「숫자로 자세히 보기」(r, B₀, B_full, R, 판정, 원인, 발현)와 「계산 과정 보기」를 펼칠 수 있다. 인쇄·PDF 저장도 된다.
- 「AI에게 결과 해석 맡기기」로 결과를 해석 프롬프트와 함께 복사한다. 사용법 탭은 원할 때만 연다.
- AI에게 보내는 글에는 찾아볼 자료 출처 10곳이 들어간다: DailyMed, FDA 약물상호작용 표, Drugs@FDA, 의약품안전나라,
  약학정보원, Flockhart 표, DrugBank, IUPHAR/BPS Guide to Pharmacology, PubMed, EMA (목록은 `docs/prompts.js`의 `SOURCES`).
- **추측 모드**(기본 꺼짐): 켜면 정확한 숫자가 없을 때 AI가 허가 라벨·논문의 설명 글(예: "주로 CYP3A4로 대사",
  "강한 억제제")을 보고 프롬프트에 적힌 추정 기준표로 값을 넣는다. 추정값은 `source`가 "추정:"으로 시작하고,
  결과에 「추정값 포함」과 개수가 표시된다.
- 화면은 항상 밝은 흰색 테마이고, 홈 화면 아이콘은 캡슐과 알약이 화살표로 서로 영향을 주는 그림이다.
- 약물 집합에 계산할 값이 없으면 숫자를 만들지 않고 「데이터가 없어서 계산하지 못했다」고 (가)·(나)별로 알려 준다.
  AI가 찾지 못한 값은 JSON의 `missing` 목록에 적는다.
- 내 컴퓨터에서 열기: `python -m http.server -d docs` 후 http://localhost:8000
- `data/`나 `config.json`을 바꾸면 `python web_build.py`로 `docs/data.js`를 다시 만든다.
- 웹앱 검사: `node --test webtest/core.test.mjs` (T1~T15, E2E-1~3). Node.js가 있으면 `python -m pytest`가
  파이썬과 웹앱의 결과·계산 과정이 똑같은지도 함께 검사한다.

## 휴대폰·패드에 앱으로 설치하기

주소: https://howardkim0125-stack.github.io/drug-interaction-calculator-/ (웹앱의 「앱 설치」 탭에도 같은 안내가 있다)

| 기기 | 방법 |
|---|---|
| 아이폰 (Safari) | 주소 열기 → 아래쪽 공유 버튼(안 보이면 「⋯」→「공유」) → 「홈 화면에 추가」 → 「추가」 |
| 아이패드 (Safari) | 주소 열기 → 오른쪽 위 공유 버튼(안 보이면 「⋯」→「공유」) → 「홈 화면에 추가」 → 「추가」 |
| 안드로이드 휴대폰·태블릿 (Chrome) | 주소 열기 → 오른쪽 위 「⋮」 → 「앱 설치」 또는 「홈 화면에 추가」 → 「설치」 |
| 갤럭시 (삼성 인터넷) | 주소 열기 → 아래쪽 「≡」 → 「현재 페이지 추가」 → 「홈 화면」 |

설치하면 주소창 없이 앱처럼 열리고, 한 번 연 뒤에는 인터넷이 없어도 열린다. 입력한 내용은 그 기기 안에만 저장된다.

## 채울 파일

- 약 정보: `data/drugs_real_template.json`을 복사해 `data/drugs_이름.json`으로 채운다(출처 `source` 칸 포함).
  작용 세기는 `c`, `e`(작용제), 또는 `F, dose, CL, tau`와 `EC50`(작용제)·`KB`(차단제) 중 하나로 적는다.
- 규칙표: `data/rules.json`
- 실제 약 쌍: `data/real_pairs_template.csv`를 복사해 채운다(용량 단위는 같은 억제제끼리 통일).
- 판정 임계값, 가상 약 범위, 숨은 요인 세기, 평가 seed: `config.json`
