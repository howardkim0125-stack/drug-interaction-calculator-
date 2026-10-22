"""계산 식 (명세 3-2 ~ 3-5, 3-7)."""
import math


# ---------------------------------------------------------------- 변환

def c_from_e(e):
    """평소 효과 크기 e → 작용 세기 c = e ÷ (1 − e)."""
    if not 0 <= e < 1:
        raise ValueError(f"e = {e}는 0 ≤ e < 1이어야 한다")
    return e / (1 - e)


def e_from_c(c):
    """작용 세기 c → 효과 크기 E = c ÷ (1 + c)."""
    return c / (1 + c)


def s_from_ki(conc, ki):
    """억제 정도 s = x ÷ (1 + x), x = 농도 ÷ Ki."""
    x = conc / ki
    return x / (1 + x)


def pk_concentration(F, dose, CL, tau):
    """평균 농도 C = F × dose ÷ (CL × tau)."""
    return F * dose / (CL * tau)


def c_from_pk(F, dose, CL, tau, ec50_or_kb):
    """작용 세기 c = C ÷ EC50 (작용제) 또는 C ÷ KB (차단제)."""
    return pk_concentration(F, dose, CL, tau) / ec50_or_kb


def scale_inhibition(s, dose_ratio):
    """용량이 dose_ratio배일 때의 억제 정도. x = s ÷ (1 − s)를 dose_ratio배 한다."""
    if dose_ratio == 1:
        return s
    x = s / (1 - s) * dose_ratio
    return x / (1 + x)


# ---------------------------------------------------------------- (가) 평균 농도 변화

def remaining_activity(inhibitions, inductions):
    """효소에 남은 작용 a = ∏(1 − s) × ∏(1 + u)."""
    a = 1.0
    for s in inhibitions:
        a *= 1 - s
    for u in inductions:
        a *= 1 + u
    return a


def r_from_fractions(parts):
    """parts = [(비율, 남은 작용), ...] → r = 1 ÷ (Σ 비율·a + (1 − Σ 비율))."""
    total = sum(f for f, _ in parts)
    return 1 / (sum(f * a for f, a in parts) + (1 - total))


def enzyme_remaining(drug, others):
    """약 B의 분해 효소마다, B를 뺀 다른 약들 때문에 남은 작용 a_간, a_장."""
    out = {}
    for enz in drug["metabolism"]:
        s_list, t_list, u_list, inhibitors, inducers = [], [], [], [], []
        for o in others:
            if o["name"] == drug["name"]:
                continue
            inh = o["inhibits"].get(enz)
            if inh:
                s = scale_inhibition(inh["s"], o["dose_ratio"])
                t = scale_inhibition(inh["t"], o["dose_ratio"])
                s_list.append(s)
                t_list.append(t)
                inhibitors.append((o["name"], s, t))
            ind = o["induces"].get(enz)
            if ind:
                u_list.append(ind["u"])
                inducers.append((o["name"], ind["u"]))
        out[enz] = {
            "f": drug["metabolism"][enz]["f"],
            "g": drug["metabolism"][enz]["g"],
            "a_liver": remaining_activity(s_list, u_list),
            "a_gut": remaining_activity(t_list, u_list),
            "inhibitors": inhibitors,
            "inducers": inducers,
        }
    return out


def concentration_ratio(drug, others):
    """약 B의 평균 농도 변화 r_간, r_장, r = r_간 × r_장."""
    rem = enzyme_remaining(drug, others)
    met = drug["metabolism"]
    r_liver = r_from_fractions([(m["f"], rem[e]["a_liver"]) for e, m in met.items()])
    r_gut = r_from_fractions([(m["g"], rem[e]["a_gut"]) for e, m in met.items()])
    return {"r_liver": r_liver, "r_gut": r_gut, "r": r_liver * r_gut, "enzymes": rem}


# ---------------------------------------------------------------- (나) 작용의 겹침

def target_effect(c_agonists, c_antagonists=()):
    """대상 하나의 작용 E = C_ag ÷ (1 + C_ag + C_ant)."""
    c_ag = sum(c_agonists)
    c_ant = sum(c_antagonists)
    return c_ag / (1 + c_ag + c_ant)


def target_actions(drugs, r_map=None):
    """대상마다 작용하는 약들의 c′ = c × r × dose_ratio와 E_P."""
    out = {}
    for d in drugs:
        r = 1.0 if r_map is None else r_map[d["name"]]
        for tgt, act in d["actions"].items():
            c2 = act["c"] * r * d["dose_ratio"]
            slot = out.setdefault(tgt, {"ag": [], "ant": []})
            slot["ag" if act["type"] == "agonist" else "ant"].append((d["name"], c2))
    for slot in out.values():
        slot["E"] = target_effect([c for _, c in slot["ag"]], [c for _, c in slot["ant"]])
    return out


def combine_sum(cs, k):
    """c_합: k = 0이면 Σc, k > 0이면 (∏(1 + k·c) − 1) ÷ k."""
    if k == 0:
        return sum(cs)
    prod = 1.0
    for c in cs:
        prod *= 1 + k * c
    return (prod - 1) / k


def combine(e_list, k):
    """대상 묶음의 작용: 각 E를 c = E ÷ (1 − E)로 바꿔 합친 뒤 c_합 ÷ (1 + c_합)."""
    c_sum = combine_sum([e / (1 - e) for e in e_list], k)
    return e_from_c(c_sum)


def effect_value(up_e, down_e, k):
    """효과 값 = (up 묶음 작용) − (down 묶음 작용)."""
    return combine(up_e, k) - combine(down_e, k)


def effect_from_targets(rule, e_map, k):
    """규칙표의 효과 하나를 대상별 E로 계산한다. 작용하는 약이 없는 대상의 E는 0."""
    up = [e_map.get(t, 0.0) for t in rule["up"]]
    down = [e_map.get(t, 0.0) for t in rule["down"]]
    return effect_value(up, down, k)


# ---------------------------------------------------------------- 3-7 거꾸로 계산

def inhibition_roots(f, g, R):
    """(1 − f·s)(1 − g·s) = 1 ÷ R의 근 전체."""
    if R <= 0:
        raise ValueError("R은 0보다 커야 한다")
    rhs = 1 - 1 / R
    if f * g == 0:
        if f + g == 0:
            raise ValueError("f, g가 모두 0이면 억제 정도를 구할 수 없다")
        return [rhs / (f + g)]
    a, b, c = f * g, -(f + g), rhs
    disc = b * b - 4 * a * c
    if disc < 0:
        raise ValueError(f"R = {R}을 만드는 실수 s가 없다")
    sq = math.sqrt(disc)
    return [(-b - sq) / (2 * a), (-b + sq) / (2 * a)]


def invert_inhibition(f, g, R):
    """보고된 평균 농도 비 R과 기질의 f, g에서 억제 정도 s(= t)를 구한다. 0 ≤ s < 1인 근만."""
    valid = [s for s in inhibition_roots(f, g, R) if 0 <= s < 1]
    if not valid:
        raise ValueError(f"f = {f}, g = {g}, R = {R}에서 0 ≤ s < 1인 근이 없다")
    return valid[0]
