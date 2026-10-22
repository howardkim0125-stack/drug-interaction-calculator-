"""숨은 진실 규칙 (명세 6-2).

시스템 코드(data_io, model, classify, interpret, explain)는 이 파일을 절대 import하지 않는다.
진짜 값은 시스템과 같은 식에 시스템이 모르는 요인 5가지를 넣어 계산한다.
식은 model.py를 쓰지 않고 이 파일에서 따로 구현한다(모든 요인을 끄면 시스템과 같아야 함).

요인과 세기:
  1 transporter     순서쌍 (A→B) 중 비율 p를 골라 진짜 r_B × (1 + m)      세기 = m
  2 k_error         효과마다 진짜 k = 규칙 k × (1 + 오차), 오차 U(−δ, δ)   세기 = δ
  3 partial_agonist 작용제 작용 중 비율 q의 최대 작용이 U(0.5, 0.9)          세기 = q
                    E_P = Σ(최대 작용 · c′) ÷ (1 + C_ag + C_ant)
  4 cascade         억제제의 진짜 r로 x = s ÷ (1 − s)를 r배 해서 s를 다시 계산,
                    수렴할 때까지 반복                                       세기 = 켬/끔
  5 noise           측정한 효과 값(B_full, 단독 값)에 U(−ε, ε)               세기 = ε
"""
import copy
import random

FACTORS = ("transporter", "k_error", "partial_agonist", "cascade", "noise")
STRENGTH_KEY = {"transporter": "m", "k_error": "delta", "partial_agonist": "q",
                "cascade": "on", "noise": "eps"}


def all_off(settings):
    s = copy.deepcopy(settings)
    for f in FACTORS:
        s[f]["on"] = False
    return s


def with_strength(settings, factor, value):
    """요인 하나의 세기를 바꾼 설정. cascade는 0이면 끔, 아니면 켬."""
    s = copy.deepcopy(settings)
    if factor == "cascade":
        s["cascade"]["on"] = bool(value)
    else:
        s[factor]["on"] = True
        s[factor][STRENGTH_KEY[factor]] = value
    return s


def strength_of(settings, factor):
    if not settings[factor]["on"]:
        return 0
    if factor == "cascade":
        return 1
    return settings[factor][STRENGTH_KEY[factor]]


def _unit(*key):
    """key마다 정해진 U(−1, 1) 값 (세기가 바뀌어도 같은 난수를 쓰기 위함)."""
    return random.Random("|".join(map(str, key))).uniform(-1, 1)


def _scale(s, mult):
    if mult == 1:
        return s
    x = s / (1 - s) * mult
    return x / (1 + x)


def _group(e_list, k):
    cs = [e / (1 - e) for e in e_list]
    if k == 0:
        c = sum(cs)
    else:
        prod = 1.0
        for ci in cs:
            prod *= 1 + k * ci
        c = (prod - 1) / k
    return c / (1 + c)


class TruthWorld:
    def __init__(self, drugs, rules, settings, seed):
        self.drugs = {d["name"]: d for d in drugs}
        self.rules = rules
        self.st = settings
        self.seed = seed
        names = sorted(self.drugs)

        # 1 수송체: 순서쌍마다 U(0,1) 하나를 뽑아 p보다 작으면 선택
        rng = random.Random(f"transporter|{seed}")
        draws = {(a, b): rng.random() for a in names for b in names if a != b}
        self.transporter_pairs = {pair for pair, u in draws.items()
                                  if u < settings["transporter"]["p"]}

        # 2 진짜 k의 오차 방향(U(−1,1)), 실제 오차 = δ × 이 값
        rng = random.Random(f"k_error|{seed}")
        self.k_unit = {eff: rng.uniform(-1, 1) for eff in sorted(rules["effects"])}

        # 3 부분 작용제: 작용제 작용마다 (선택용 U(0,1), 최대 작용)
        rng = random.Random(f"partial|{seed}")
        lo, hi = settings["partial_agonist"]["emax"]
        self.partial_draw = {}
        for n in names:
            for tgt in sorted(self.drugs[n]["actions"]):
                if self.drugs[n]["actions"][tgt]["type"] == "agonist":
                    self.partial_draw[(n, tgt)] = (rng.random(), rng.uniform(lo, hi))

    # ------------------------------------------------------------ 숨은 요인 값

    def transporter_factor(self, a, b):
        tr = self.st["transporter"]
        if tr["on"] and (a, b) in self.transporter_pairs:
            return 1 + tr["m"]
        return 1.0

    def true_k(self, eff):
        k = self.rules["effects"][eff]["k"]
        ke = self.st["k_error"]
        if not ke["on"]:
            return k
        return max(0.0, k * (1 + ke["delta"] * self.k_unit[eff]))

    def emax(self, name, tgt):
        pa = self.st["partial_agonist"]
        if not pa["on"]:
            return 1.0
        u, value = self.partial_draw[(name, tgt)]
        return value if u < pa["q"] else 1.0

    def noise(self, *key):
        nz = self.st["noise"]
        if not nz["on"] or nz["eps"] == 0:
            return 0.0
        return nz["eps"] * _unit("noise", self.seed, *key)

    # ------------------------------------------------------------ (가) 평균 농도

    def _ratio(self, b, names, conc):
        drug = self.drugs[b]
        liver, gut = [], []
        for enz, m in drug["metabolism"].items():
            a_l = a_g = 1.0
            for a in names:
                if a == b:
                    continue
                other = self.drugs[a]
                inh = other["inhibits"].get(enz)
                if inh:
                    mult = other["dose_ratio"] * (conc[a] if conc is not None else 1.0)
                    a_l *= 1 - _scale(inh["s"], mult)
                    a_g *= 1 - _scale(inh["t"], mult)
                ind = other["induces"].get(enz)
                if ind:
                    a_l *= 1 + ind["u"]
                    a_g *= 1 + ind["u"]
            liver.append((m["f"], a_l))
            gut.append((m["g"], a_g))
        r_l = 1 / (sum(f * a for f, a in liver) + 1 - sum(f for f, _ in liver))
        r_g = 1 / (sum(g * a for g, a in gut) + 1 - sum(g for g, _ in gut))
        r = r_l * r_g
        for a in names:
            if a != b:
                r *= self.transporter_factor(a, b)
        return r

    def ratios(self, names):
        """진짜 r. 연쇄가 켜져 있으면 억제제 자신의 농도 변화를 반영해 수렴까지 반복."""
        ca = self.st["cascade"]
        if not ca["on"]:
            return {n: self._ratio(n, names, None) for n in names}, True, 1
        r = {n: 1.0 for n in names}
        for it in range(1, ca["max_iter"] + 1):
            new = {n: self._ratio(n, names, r) for n in names}
            diff = max(abs(new[n] - r[n]) for n in names)
            r = new
            if diff < ca["tol"]:
                return r, True, it
        return r, False, ca["max_iter"]

    # ------------------------------------------------------------ (나) 작용의 겹침

    def effect_values(self, names, r, rule_k=True):
        num, c_ag, c_ant = {}, {}, {}
        for n in names:
            d = self.drugs[n]
            for tgt, act in d["actions"].items():
                c2 = act["c"] * r[n] * d["dose_ratio"]
                if act["type"] == "agonist":
                    num[tgt] = num.get(tgt, 0.0) + self.emax(n, tgt) * c2
                    c_ag[tgt] = c_ag.get(tgt, 0.0) + c2
                else:
                    c_ant[tgt] = c_ant.get(tgt, 0.0) + c2
        e_map = {t: num.get(t, 0.0) / (1 + c_ag.get(t, 0.0) + c_ant.get(t, 0.0))
                 for t in set(c_ag) | set(c_ant)}
        out = {}
        for eff, rule in self.rules["effects"].items():
            k = self.true_k(eff) if rule_k else 1.0
            up = [e_map.get(t, 0.0) for t in rule["up"]]
            down = [e_map.get(t, 0.0) for t in rule["down"]]
            out[eff] = _group(up, k) - _group(down, k)
        return out

    # ------------------------------------------------------------ 진짜 값 전체

    def evaluate(self, names):
        """함께 먹는 약 이름 목록의 진짜 값.

        B0: 진짜 세계에서 r = 1, k = 1(부분 작용제는 반영, 측정 오차 없음)
        Bfull: 진짜 r, 진짜 k에 측정 오차를 더한 값
        singles: 약 하나씩 먹었을 때 측정한 값(측정 오차 포함)
        """
        names = list(names)
        r, converged, iters = self.ratios(names)
        ones = {n: 1.0 for n in names}
        b0 = self.effect_values(names, ones, rule_k=False)
        clean = self.effect_values(names, r, rule_k=True)
        combo = "+".join(sorted(names))
        bfull = {eff: v + self.noise("combo", combo, eff) for eff, v in clean.items()}
        singles = {}
        for n in names:
            alone = self.effect_values([n], {n: 1.0}, rule_k=True)
            singles[n] = {eff: v + self.noise("single", n, eff) for eff, v in alone.items()}
        return {"r": r, "converged": converged, "iterations": iters,
                "B0": b0, "Bfull": bfull, "Bfull_clean": clean, "singles": singles}
