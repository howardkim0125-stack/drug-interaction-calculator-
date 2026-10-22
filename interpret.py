"""전체 계산과 판정 (명세 3-2 ~ 3-6)."""
import model
from classify import classify
from data_io import check_targets

INCREASE, DECREASE, INDEPENDENT = "증강", "감소", "독립"


def drug_ratios(drugs):
    """각 약의 평균 농도 변화. 억제제의 s·t는 원래 농도 기준(연쇄 없음)."""
    return {d["name"]: model.concentration_ratio(d, drugs) for d in drugs}


def effect_values(drugs, rules, r_map=None, rule_k=True):
    """모든 효과의 값. r_map=None이면 모든 r = 1, rule_k=False면 모든 k = 1."""
    tacts = model.target_actions(drugs, r_map)
    e_map = {t: v["E"] for t, v in tacts.items()}
    vals = {}
    for eff, rule in rules["effects"].items():
        k = rule["k"] if rule_k else 1.0
        vals[eff] = model.effect_from_targets(rule, e_map, k)
    return vals, tacts


def judge(b0, bfull, cfg):
    """판정. |B₀|가 크면 비율 R, 작으면 B₀ 방향 기준 차이 d로 본다."""
    j = cfg["judgement"]
    if abs(b0) >= j["b0_small"]:
        R = bfull / b0
        if R > j["ratio_up"]:
            return INCREASE, R, None
        if R < j["ratio_down"]:
            return DECREASE, R, None
        return INDEPENDENT, R, None
    sign = -1.0 if b0 < 0 else 1.0
    d = (bfull - b0) * sign
    if abs(d) < j["diff_small"]:
        return INDEPENDENT, None, d
    return (INCREASE if d > 0 else DECREASE), None, d


def cause_label(verdict, r_contrib, k_contrib, cfg):
    if verdict == INDEPENDENT:
        return "-"
    lim = cfg["judgement"]["cause_min"]
    parts = [n for n, v in (("r", r_contrib), ("k", k_contrib)) if abs(v) >= lim]
    return "+".join(parts) if parts else "없음"


def manifestation(rule, singles, b0, bfull):
    """발현 판정. threshold가 있는 효과만."""
    thr = rule["threshold"]
    if thr is None:
        return None, "-"
    over = [n for n, v in singles.items() if abs(v) >= thr]
    if over:
        return False, f"단독으로 이미 기준 이상({', '.join(over)})"
    if abs(bfull) < thr:
        return False, "기준 미만"
    if abs(b0) >= thr:
        return True, "더하기만으로 발현"
    return True, "상호작용 때문에 발현"


def r_flag(r, cfg):
    if r >= cfg["flag"]["r_high"]:
        return "평균 농도 증가"
    if r <= cfg["flag"]["r_low"]:
        return "평균 농도 감소"
    return None


def analyze(drugs, rules, cfg, check=True):
    """함께 먹는 약 목록 전체를 계산한다."""
    if check:
        check_targets(drugs, rules)
    ratios = drug_ratios(drugs)
    for info in ratios.values():
        info["flag"] = r_flag(info["r"], cfg)
    r_map = {n: v["r"] for n, v in ratios.items()}

    b0_vals, t0 = effect_values(drugs, rules, None, rule_k=False)
    br_vals, _ = effect_values(drugs, rules, r_map, rule_k=False)
    bf_vals, tf = effect_values(drugs, rules, r_map, rule_k=True)
    singles = {d["name"]: effect_values([d], rules, None, rule_k=True)[0] for d in drugs}

    effects = []
    for eff, rule in rules["effects"].items():
        b0, br, bf = b0_vals[eff], br_vals[eff], bf_vals[eff]
        verdict, R, d = judge(b0, bf, cfg)
        r_c, k_c = br - b0, bf - br
        targets = {}
        for direction in ("up", "down"):
            for t in rule[direction]:
                if t in tf:
                    targets[t] = {"dir": direction, "E0": t0[t]["E"], "E": tf[t]["E"],
                                  "ag": tf[t]["ag"], "ant": tf[t]["ant"]}
        involved = sorted({n for t in targets.values() for n, _ in t["ag"] + t["ant"]})
        eff_singles = {n: singles[n][eff] for n in involved}
        shown, kind = manifestation(rule, eff_singles, b0, bf)
        effects.append({
            "effect": eff, "rule": rule, "B0": b0, "Br": br, "Bfull": bf,
            "verdict": verdict, "R": R, "d": d,
            "r_contrib": r_c, "k_contrib": k_c,
            "cause": cause_label(verdict, r_c, k_c, cfg),
            "manifest": shown, "manifest_kind": kind,
            "singles": eff_singles, "targets": targets, "involved": involved,
        })
    return {
        "drugs": [d["name"] for d in drugs],
        "classification": classify(drugs, rules),
        "ratios": ratios,
        "effects": effects,
    }
