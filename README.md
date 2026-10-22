# 약물 상호작용 계산 시스템 (수학 탐구)

> 수학 탐구 모델의 결과이며 실제 복약 판단이 아니다.

## 준비

```
pip install -r requirements.txt
```

## 실행

| 명령 | 하는 일 | 결과 |
|---|---|---|
| `python -m pytest` | 테스트 전체(T1~T15, E2E-1~3 등) | 화면 |
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

## 채울 파일

- 약 정보: `data/drugs_real_template.json`을 복사해 `data/drugs_이름.json`으로 채운다(출처 `source` 칸 포함).
  작용 세기는 `c`, `e`(작용제), 또는 `F, dose, CL, tau`와 `EC50`(작용제)·`KB`(차단제) 중 하나로 적는다.
- 규칙표: `data/rules.json`
- 실제 약 쌍: `data/real_pairs_template.csv`를 복사해 채운다(용량 단위는 같은 억제제끼리 통일).
- 판정 임계값, 가상 약 범위, 숨은 요인 세기, 평가 seed: `config.json`
