"""계산 과정 출력(--trace): 중간값을 식 순서대로 "식에 숫자를 넣은 모습 = 결과"로 적는다."""
import model
from classify import format_classification
from data_io import DISCLAIMER
from interpret import INDEPENDENT

MINUS = "−"


def num(x):
    """숫자 표시(유효숫자 4자리, 음수는 −)."""
    text = f"{x:.4g}"
    if text in ("-0", "-0.0"):
        text = "0"
    return text.replace("-", MINUS)


def par(x):
    """식 안의 음수는 괄호로 감싼다."""
    return f"({num(x)})" if x < 0 else num(x)


class Trace:
    def __init__(self):
        self.lines = []

    def h(self, level, text):
        if self.lines and self.lines[-1] != "":
            self.lines.append("")
        self.lines += [f"{'#' * level} {text}", ""]

    def eq(self, text):
        self.lines.append(f"- {text}")

    def raw(self, text):
        self.lines.append(text)

    def text(self):
        return "\n".join(self.lines).strip() + "\n"


# ---------------------------------------------------------------- 0. 입력 변환

def input_section(t, drugs):
    t.h(2, "0. 입력 변환")
    before = len(t.lines)
    for d in drugs:
        n = d["name"]
        for tgt, act in d["actions"].items():
            g = act.get("input")
            if act.get("way") == "e":
                t.eq(f"c({n}, {tgt}) = e ÷ (1 − e) = {num(g['e'])} ÷ (1 − {num(g['e'])}) = {num(act['c'])}")
            elif act.get("way") == "pk":
                key = "EC50" if act["type"] == "agonist" else "KB"
                t.eq(f"C({n}) = F × dose ÷ (CL × tau) = {num(g['F'])} × {num(g['dose'])} ÷ "
                     f"({num(g['CL'])} × {num(g['tau'])}) = {num(g['C'])}")
                t.eq(f"c({n}, {tgt}) = C ÷ {key} = {num(g['C'])} ÷ {num(g[key])} = {num(act['c'])}")
        for enz, inh in d["inhibits"].items():
            g = inh.get("ki_input")
            if g:
                for site, conc, val in (("간", "conc_liver", inh["s"]), ("장", "conc_gut", inh["t"])):
                    x = g[conc] / g["Ki"]
                    t.eq(f"x_{site}({n}, {enz}) = {conc} ÷ Ki = {num(g[conc])} ÷ {num(g['Ki'])} = {num(x)}, "
                         f"{'s' if site == '간' else 't'} = x ÷ (1 + x) = {num(x)} ÷ (1 + {num(x)}) = {num(val)}")
            if d["dose_ratio"] != 1:
                for key in ("s", "t"):
                    v = inh[key]
                    x = v / (1 - v) * d["dose_ratio"]
                    t.eq(f"{key}({n}, {enz}, 용량 {num(d['dose_ratio'])}배): x = {key} ÷ (1 − {key}) × dose_ratio = "
                         f"{num(v)} ÷ (1 − {num(v)}) × {num(d['dose_ratio'])} = {num(x)}, "
                         f"{key} = x ÷ (1 + x) = {num(model.scale_inhibition(v, d['dose_ratio']))}")
    if len(t.lines) == before:
        t.eq("변환할 입력 없음 (c, s, t를 직접 입력)")


# ---------------------------------------------------------------- 2·3. 효소와 r

def ratio_section(t, drugs):
    t.h(2, "2. 효소별 남은 작용 a_간, a_장")
    infos = {}
    for d in drugs:
        info = model.concentration_ratio(d, drugs)
        infos[d["name"]] = info
        t.h(3, d["name"])
        if not d["metabolism"]:
            t.eq("분해 효소 정보 없음")
            continue
        for enz, rem in info["enzymes"].items():
            if not rem["inhibitors"] and not rem["inducers"]:
                t.eq(f"a_간({enz}) = a_장({enz}) = 1 (억제·유도하는 다른 약 없음)")
                continue
            who = [f"{n} 억제" for n, _, _ in rem["inhibitors"]] + [f"{n} 유도" for n, _ in rem["inducers"]]
            for site, key, idx in (("간", "a_liver", 1), ("장", "a_gut", 2)):
                factors = [f"(1 − {num(x[idx])})" for x in rem["inhibitors"]]
                factors += [f"(1 + {num(u)})" for _, u in rem["inducers"]]
                t.eq(f"a_{site}({enz}) = {' × '.join(factors)} = {num(rem[key])}  ← {', '.join(who)}")

    t.h(2, "3. 평균 농도 변화 r_간, r_장, r")
    for d in drugs:
        n = d["name"]
        info = infos[n]
        rem = info["enzymes"]
        if not any(r["inhibitors"] or r["inducers"] for r in rem.values()):
            t.eq(f"r_간({n}) = r_장({n}) = r({n}) = 1 (분해 효소를 바꾸는 다른 약 없음)")
            continue
        for site, frac, key, val in (("간", "f", "a_liver", info["r_liver"]), ("장", "g", "a_gut", info["r_gut"])):
            terms = [f"{num(rem[e][frac])} × {num(rem[e][key])}" for e in rem]
            rest = 1 - sum(rem[e][frac] for e in rem)
            t.eq(f"r_{site}({n}) = 1 ÷ ({' + '.join(terms)} + {num(max(rest, 0.0))}) = {num(val)}")
        t.eq(f"r({n}) = r_간 × r_장 = {num(info['r_liver'])} × {num(info['r_gut'])} = {num(info['r'])}")
    return {n: v["r"] for n, v in infos.items()}


# ---------------------------------------------------------------- 4. 대상

def target_lines(t, drugs, r_map, only=None):
    """대상별 c′, C_ag, C_ant, E_P. r_map=None이면 r = 1."""
    by_name = {d["name"]: d for d in drugs}
    tacts = model.target_actions(drugs, r_map)
    for tgt in sorted(tacts):
        if only is not None and tgt not in only:
            continue
        slot = tacts[tgt]
        for name, c2 in slot["ag"] + slot["ant"]:
            d = by_name[name]
            r = 1.0 if r_map is None else r_map[name]
            kind = "작용제" if d["actions"][tgt]["type"] == "agonist" else "차단제"
            t.eq(f"c′({name}, {tgt}, {kind}) = c × r × dose_ratio = {num(d['actions'][tgt]['c'])} × "
                 f"{num(r)} × {num(d['dose_ratio'])} = {num(c2)}")
        c_ag = sum(c for _, c in slot["ag"])
        c_ant = sum(c for _, c in slot["ant"])
        for label, items, total in (("C_ag", slot["ag"], c_ag), ("C_ant", slot["ant"], c_ant)):
            if len(items) > 1:
                t.eq(f"{label}({tgt}) = {' + '.join(num(c) for _, c in items)} = {num(total)}")
            else:
                t.eq(f"{label}({tgt}) = {num(total)}")
        t.eq(f"E({tgt}) = C_ag ÷ (1 + C_ag + C_ant) = {num(c_ag)} ÷ (1 + {num(c_ag)} + {num(c_ant)}) "
             f"= {num(slot['E'])}")
    return {tg: v["E"] for tg, v in tacts.items()}


# ---------------------------------------------------------------- 5. 효과

def group_lines(t, label, targets, e_map, k):
    present = [(tg, e_map[tg]) for tg in targets if e_map.get(tg, 0.0) > 0]
    absent = [tg for tg in targets if e_map.get(tg, 0.0) == 0]
    if not present:
        t.eq(f"{label} 묶음 작용 = 0 (작용하는 대상 없음)")
        return 0.0
    cs = []
    for tg, e in present:
        c = e / (1 - e)
        cs.append(c)
        t.eq(f"c({tg}) = E ÷ (1 − E) = {num(e)} ÷ (1 − {num(e)}) = {num(c)}")
    c_sum = model.combine_sum(cs, k)
    if len(cs) == 1:
        t.eq(f"c_합({label}) = c({present[0][0]}) = {num(c_sum)} (대상 1개)")
    elif k == 0:
        t.eq(f"c_합({label}) = {' + '.join(num(c) for c in cs)} = {num(c_sum)} (k = 0)")
    else:
        prod = " × ".join(f"(1 + {num(k)} × {num(c)})" for c in cs)
        t.eq(f"c_합({label}) = ({prod} − 1) ÷ {num(k)} = {num(c_sum)}")
    act = model.e_from_c(c_sum)
    t.eq(f"{label} 묶음 작용 = c_합 ÷ (1 + c_합) = {num(c_sum)} ÷ (1 + {num(c_sum)}) = {num(act)}")
    if absent:
        t.eq(f"(작용하는 약이 없는 대상 {', '.join(absent)}는 E = 0이라 뺌)")
    return act


def effect_lines(t, name, rule, e_map, k, symbol):
    up = group_lines(t, "up", rule["up"], e_map, k)
    down = group_lines(t, "down", rule["down"], e_map, k) if rule["down"] else 0.0
    if not rule["down"]:
        t.eq("down 묶음 작용 = 0 (down 대상 없음)")
    val = up - down
    t.eq(f"{symbol} = (up 묶음 작용) − (down 묶음 작용) = {num(up)} − {par(down)} = {num(val)}")
    return val


# ---------------------------------------------------------------- 전체

def build(drugs, rules, cfg, res):
    """res는 interpret.analyze 결과(판정·발현 값 확인용)."""
    j = cfg["judgement"]
    t = Trace()
    names = [d["name"] for d in drugs]
    t.raw(f"# 계산 과정: {' + '.join(names)}")
    input_section(t, drugs)

    t.h(2, "1. 분류")
    t.raw("```")
    t.raw(format_classification(res["classification"]))
    t.raw("```")

    r_map = ratio_section(t, drugs)
    effects = [e for e in res["effects"] if e["involved"]]
    used = {tg for e in effects for tg in e["rule"]["up"] + e["rule"]["down"]}

    t.h(2, "4. 대상별 작용 C_ag, C_ant, E_P")
    t.h(3, "기준 (모든 r = 1)")
    e0 = target_lines(t, drugs, None, used)
    t.h(3, "실제 (r 반영)")
    ef = target_lines(t, drugs, r_map, used)

    t.h(2, "5. 효과별 합치기 cᵢ, c_합, 묶음 작용")
    values = {}
    for e in effects:
        rule = e["rule"]
        down = ", ".join(rule["down"]) or "없음"
        t.h(3, f"{e['effect']} (up: {', '.join(rule['up'])} / down: {down}, 규칙표 k = {num(rule['k'])})")
        t.raw("**B₀ (r = 1, k = 1)**")
        t.raw("")
        b0 = effect_lines(t, e["effect"], rule, e0, 1.0, "B₀")
        t.raw("")
        t.raw("**B_r (실제 r, k = 1)**")
        t.raw("")
        br = effect_lines(t, e["effect"], rule, ef, 1.0, "B_r")
        t.raw("")
        t.raw(f"**B_full (실제 r, k = {num(rule['k'])})**")
        t.raw("")
        bf = effect_lines(t, e["effect"], rule, ef, rule["k"], "B_full")
        values[e["effect"]] = (b0, br, bf)

    t.h(2, "6. B₀, B_r, B_full과 판정")
    for e in effects:
        b0, br, bf = values[e["effect"]]
        t.h(3, e["effect"])
        t.eq(f"B₀ = {num(b0)}, B_r = {num(br)}, B_full = {num(bf)}")
        if abs(b0) >= j["b0_small"]:
            t.eq(f"|B₀| = {num(abs(b0))} ≥ {num(j['b0_small'])} → 비율로 판정")
            R = bf / b0
            t.eq(f"R = B_full ÷ B₀ = {num(bf)} ÷ {par(b0)} = {num(R)}")
            if R > j["ratio_up"]:
                t.eq(f"R = {num(R)} > {num(j['ratio_up'])} → {e['verdict']}")
            elif R < j["ratio_down"]:
                t.eq(f"R = {num(R)} < {num(j['ratio_down'])} → {e['verdict']}")
            else:
                t.eq(f"{num(j['ratio_down'])} ≤ R = {num(R)} ≤ {num(j['ratio_up'])} → {e['verdict']}")
        else:
            sign = -1 if b0 < 0 else 1
            d = (bf - b0) * sign
            t.eq(f"|B₀| = {num(abs(b0))} < {num(j['b0_small'])} → 차이로 판정")
            t.eq(f"d = (B_full − B₀) × 부호(B₀) = ({num(bf)} − {par(b0)}) × {par(sign)} = {num(d)}")
            if abs(d) < j["diff_small"]:
                t.eq(f"|d| = {num(abs(d))} < {num(j['diff_small'])} → {e['verdict']}")
            else:
                t.eq(f"|d| = {num(abs(d))} ≥ {num(j['diff_small'])}, d {'> 0' if d > 0 else '< 0'} → {e['verdict']}")
        t.eq(f"r 기여 = B_r − B₀ = {num(br)} − {par(b0)} = {num(br - b0)}")
        t.eq(f"k 기여 = B_full − B_r = {num(bf)} − {par(br)} = {num(bf - br)}")
        if e["verdict"] == INDEPENDENT:
            t.eq("원인: - (판정이 독립)")
        else:
            t.eq(f"원인: |기여| ≥ {num(j['cause_min'])}인 것 → {e['cause']}")

    t.h(2, "7. 발현")
    for e in effects:
        rule = e["rule"]
        thr = rule["threshold"]
        t.h(3, e["effect"])
        if thr is None:
            t.eq("threshold 없음 → 판정하지 않음")
            continue
        for n in e["involved"]:
            d = next(x for x in drugs if x["name"] == n)
            if t.lines[-1] != "":
                t.raw("")
            t.raw(f"**단독({n})**")
            t.raw("")
            e_single = target_lines(t, [d], None, set(rule["up"] + rule["down"]))
            effect_lines(t, e["effect"], rule, e_single, rule["k"], f"단독({n})")
        t.raw("")
        singles = e["singles"]
        over = [n for n, v in singles.items() if abs(v) >= thr]
        listing = ", ".join(f"{n} {num(abs(v))}" for n, v in singles.items())
        if over:
            t.eq(f"|단독 값| = {listing} → {', '.join(over)}가 {num(thr)} 이상 → 발현 아님(단독으로 이미 기준 이상)")
            continue
        t.eq(f"|단독 값| = {listing} → 모두 < {num(thr)}")
        bf, b0 = e["Bfull"], e["B0"]
        if abs(bf) < thr:
            t.eq(f"|B_full| = {num(abs(bf))} < {num(thr)} → 발현 아님")
            continue
        t.eq(f"|B_full| = {num(abs(bf))} ≥ {num(thr)} → 발현")
        if abs(b0) >= thr:
            t.eq(f"|B₀| = {num(abs(b0))} ≥ {num(thr)} → 더하기만으로 발현")
        else:
            t.eq(f"|B₀| = {num(abs(b0))} < {num(thr)} → 상호작용 때문에 발현")

    t.raw("")
    t.raw(DISCLAIMER)
    return t.text(), values
