"""평가 (명세 6-3): 시스템 값과 숨은 진실 값을 비교한다.

이 파일은 평가 도구이며 시스템 코드가 아니다(진실 규칙을 import하는 것은 여기뿐).
"""
import copy
import math
import random
from itertools import combinations
from math import comb

import interpret
from virtual import generator
from virtual import truth as truth_mod

VERDICTS = (interpret.INCREASE, interpret.DECREASE, interpret.INDEPENDENT)

METRICS = [
    ("mech_precision", "기전 수준 정밀도"),
    ("mech_recall", "기전 수준 재현율"),
    ("mech_accuracy", "기전 수준 정확도"),
    ("judge_precision", "판정 수준 정밀도"),
    ("judge_recall", "판정 수준 재현율"),
    ("judge_accuracy", "판정 수준 정확도"),
    ("mae_r", "r 평균절대오차"),
    ("mae_effect", "효과 값 평균절대오차"),
    ("verdict_agreement", "판정 일치율(3×3)"),
    ("manifest_precision", "발현 정밀도"),
    ("manifest_recall", "발현 재현율"),
]


def _ratio(num, den):
    return num / den if den else math.nan


def binary_scores(tp, fp, fn, tn):
    return {"precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn),
            "accuracy": _ratio(tp + tn, tp + fp + fn + tn),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def pick_combos(drugs, triples=0, seed=0):
    """2약 조합 전체와 무작위 3약 조합 일부."""
    combos = [list(c) for c in combinations(drugs, 2)]
    if triples:
        idx = list(combinations(range(len(drugs)), 3))
        rng = random.Random(f"triples|{seed}")
        for t in sorted(rng.sample(idx, min(triples, comb(len(drugs), 3)))):
            combos.append([drugs[i] for i in t])
    return combos


def system_results(combos, rules, cfg):
    """시스템 계산 결과. 진실 설정과 무관하므로 스트레스 시험에서 재사용한다."""
    return [interpret.analyze(c, rules, cfg, check=False) for c in combos]


MODELS = ("system", "simple_sum", "proportional")
MODEL_KO = {"system": "현재 시스템", "simple_sum": "비교 1: 단순 합산", "proportional": "비교 2: 비례 모델"}


def clip(x):
    return max(-1.0, min(1.0, x))


def predict(sys, model, cfg):
    """한 조합에 대한 모델의 예측: r, 평균 농도를 바꾸는 쌍, 효과별 B₀·B_full·판정·발현.

    system       현재 시스템(판정은 cfg 기준으로 다시 계산)
    simple_sum   r = 1, 효과 값 = clip(Σ 단독 값), 기준값도 같은 식(r = 1)
    proportional 효과 값 = clip(Σ r × 단독 값), 기준값 = clip(Σ 단독 값)
    단독 값은 시스템이 계산한 '약 하나만 먹었을 때의 효과 값'이다.
    """
    names = sys["drugs"]
    r_sys = {n: sys["ratios"][n]["r"] for n in names}
    pairs_sys = {(c["from"], c["to"]) for c in sys["classification"]["concentration"]}
    if model == "simple_sum":
        r, pairs = {n: 1.0 for n in names}, set()
    else:
        r, pairs = r_sys, pairs_sys
    effects = []
    for e in sys["effects"]:
        if not e["involved"]:
            continue
        singles = e["singles"]
        if model == "system":
            b0, bf = e["B0"], e["Bfull"]
        elif model == "simple_sum":
            b0 = bf = clip(sum(singles.values()))
        else:
            b0 = clip(sum(singles.values()))
            bf = clip(sum(r[n] * v for n, v in singles.items()))
        verdict = interpret.judge(b0, bf, cfg)[0]
        shown = interpret.manifestation(e["rule"], singles, b0, bf)[0]
        effects.append({"effect": e["effect"], "rule": e["rule"], "involved": e["involved"],
                        "B0": b0, "Bfull": bf, "verdict": verdict, "manifest": shown})
    return {"drugs": names, "r": r, "pairs": pairs, "effects": effects}


def truth_results(sys_results, world):
    return [world.evaluate(s["drugs"]) for s in sys_results]


def compare(sys_results, rules, world, cfg, model="system", truths=None):
    """모델 예측과 진짜 값을 비교해 지표와 상세 행을 만든다."""
    tol = cfg["evaluate"]["affect_tol"]
    if truths is None:
        truths = truth_results(sys_results, world)
    mech = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    judge = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    mani = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    confusion = {(s, t): 0 for s in VERDICTS for t in VERDICTS}
    r_err, e_err = [], []
    pair_rows, effect_rows = [], []
    nonconverged = 0

    def count(box, predicted, actual):
        key = ("tp" if actual else "fp") if predicted else ("fn" if actual else "tn")
        box[key] += 1

    for sys, tru in zip(sys_results, truths):
        pred = predict(sys, model, cfg)
        names = pred["drugs"]
        nonconverged += not tru["converged"]
        combo = "+".join(names)
        for n in names:
            r_err.append(abs(pred["r"][n] - tru["r"][n]))

        if len(names) == 2:
            for a, b in ((names[0], names[1]), (names[1], names[0])):
                actual = abs(tru["r"][b] - 1) > tol
                predicted = (a, b) in pred["pairs"]
                count(mech, predicted, actual)
                pair_rows.append([a, b, int(predicted), int(actual), pred["r"][b], tru["r"][b],
                                  int((a, b) in world.transporter_pairs)])

        for e in pred["effects"]:
            eff = e["effect"]
            t_b0, t_bf = tru["B0"][eff], tru["Bfull"][eff]
            t_verdict = interpret.judge(t_b0, t_bf, cfg)[0]
            confusion[(e["verdict"], t_verdict)] += 1
            count(judge, e["verdict"] != interpret.INDEPENDENT, t_verdict != interpret.INDEPENDENT)
            e_err.append(abs(e["Bfull"] - t_bf))
            t_shown = None
            if e["rule"]["threshold"] is not None:
                t_singles = {n: tru["singles"][n][eff] for n in e["involved"]}
                t_shown = interpret.manifestation(e["rule"], t_singles, t_b0, t_bf)[0]
                count(mani, bool(e["manifest"]), bool(t_shown))
            effect_rows.append([combo, eff, e["B0"], e["Bfull"], t_b0, t_bf, e["verdict"], t_verdict,
                                "" if e["manifest"] is None else int(e["manifest"]),
                                "" if t_shown is None else int(t_shown)])

    m = binary_scores(**mech)
    j = binary_scores(**judge)
    a = binary_scores(**mani)
    n_eff = sum(confusion.values())
    metrics = {
        "mech_precision": m["precision"], "mech_recall": m["recall"], "mech_accuracy": m["accuracy"],
        "judge_precision": j["precision"], "judge_recall": j["recall"], "judge_accuracy": j["accuracy"],
        "mae_r": _ratio(sum(r_err), len(r_err)),
        "mae_effect": _ratio(sum(e_err), len(e_err)),
        "verdict_agreement": _ratio(sum(confusion[(v, v)] for v in VERDICTS), n_eff),
        "manifest_precision": a["precision"], "manifest_recall": a["recall"],
    }
    return {
        "metrics": metrics, "counts": {"mech": m, "judge": j, "manifest": a},
        "confusion": confusion, "n_combos": len(sys_results), "n_effect_rows": n_eff,
        "nonconverged": nonconverged, "pair_rows": pair_rows, "effect_rows": effect_rows,
    }


def build_world(seed, cfg, settings, n_drugs, triples=0):
    """가상 세계 하나: 시스템 결과, 숨은 진실, 진짜 값."""
    drugs, rules = generator.generate(seed, cfg["virtual"], n_drugs)
    combos = pick_combos(drugs, triples, seed)
    sys = system_results(combos, rules, cfg)
    world = truth_mod.TruthWorld(drugs, rules, settings, seed)
    return {"seed": seed, "rules": rules, "sys": sys, "world": world,
            "truths": truth_results(sys, world)}


def evaluate_world(seed, cfg, settings, n_drugs, triples=0, model="system"):
    b = build_world(seed, cfg, settings, n_drugs, triples)
    return compare(b["sys"], b["rules"], b["world"], cfg, model, b["truths"])


def compare_models(worlds, cfg, models=MODELS):
    """같은 숨은 세계에서 모델마다 같은 지표를 계산한다."""
    runs = []
    for b in worlds:
        for model in models:
            res = compare(b["sys"], b["rules"], b["world"], cfg, model, b["truths"])
            runs.append({"model": model, "seed": b["seed"], **res["metrics"]})
    return runs


def with_ratio_thresholds(cfg, up, down):
    out = copy.deepcopy(cfg)
    out["judgement"]["ratio_up"] = up
    out["judgement"]["ratio_down"] = down
    return out


def sensitivity(worlds, cfg, thresholds):
    """판정 비율 기준을 바꿔(시스템·진짜 양쪽) 판정 지표를 다시 계산한다."""
    runs = []
    for up, down in thresholds:
        c2 = with_ratio_thresholds(cfg, up, down)
        for b in worlds:
            res = compare(b["sys"], b["rules"], b["world"], c2, "system", b["truths"])
            runs.append({"thresholds": f"{up:g}/{down:g}", "seed": b["seed"], **res["metrics"]})
    return runs


def summarize_by(runs, key, metrics):
    """key마다 지표의 평균·최솟값·최댓값(NaN 제외)."""
    groups = {}
    for run in runs:
        groups.setdefault(run[key], []).append(run)
    rows = []
    for g, items in groups.items():
        for m in metrics:
            vals = [x[m] for x in items if not math.isnan(x[m])]
            if vals:
                rows.append([g, m, sum(vals) / len(vals), min(vals), max(vals), len(vals)])
            else:
                rows.append([g, m, math.nan, math.nan, math.nan, 0])
    return [key, "metric", "mean", "min", "max", "n_seeds"], rows


def stress(cfg, factors=truth_mod.FACTORS, seeds=None, strengths=None, n_drugs=None,
           triples=None, progress=None):
    """숨은 요인 하나의 세기만 바꾸고 나머지 요인은 끈 채 seed마다 반복한다.

    cascade는 켬/끔만 있으므로 세기 0(끔), 1(켬) 두 값으로 본다.
    """
    sc = cfg["evaluate"]["stress"]
    seeds = sc["seeds"] if seeds is None else seeds
    strengths = sc["strengths"] if strengths is None else strengths
    n_drugs = sc["n_drugs"] if n_drugs is None else n_drugs
    triples = sc["triples"] if triples is None else triples
    base = truth_mod.all_off(cfg["truth"])

    runs = []
    for seed in seeds:
        drugs, rules = generator.generate(seed, cfg["virtual"], n_drugs)
        combos = pick_combos(drugs, triples, seed)
        sys = system_results(combos, rules, cfg)
        for factor in factors:
            levels = [0, 1] if factor == "cascade" else strengths
            for level in levels:
                st = truth_mod.with_strength(base, factor, level)
                world = truth_mod.TruthWorld(drugs, rules, st, seed)
                res = compare(sys, rules, world, cfg, "system")
                runs.append({"factor": factor, "strength": level, "seed": seed,
                             "nonconverged": res["nonconverged"], **res["metrics"]})
                if progress:
                    progress(factor, level, seed)
    return runs


def summarize(runs):
    """(요인, 세기)마다 지표의 평균·최솟값·최댓값. NaN은 빼고 계산한다."""
    groups = {}
    for run in runs:
        groups.setdefault((run["factor"], run["strength"]), []).append(run)
    rows = []
    for (factor, strength), items in groups.items():
        for key, _ in METRICS:
            vals = [x[key] for x in items if not math.isnan(x[key])]
            if vals:
                rows.append([factor, strength, key, sum(vals) / len(vals), min(vals), max(vals), len(vals)])
            else:
                rows.append([factor, strength, key, math.nan, math.nan, math.nan, 0])
    return ["factor", "strength", "metric", "mean", "min", "max", "n_seeds"], rows
