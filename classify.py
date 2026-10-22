"""분류 (명세 3-1): 이름 교집합만 보고 값은 보지 않는다."""
from itertools import combinations

from tables import format_table

TYPE_KO = {"agonist": "작용제", "antagonist": "차단제"}


def concentration_pairs(drugs):
    """A의 (inhibits ∪ induces) ∩ B의 metabolism ≠ ∅ 인 순서쌍 (A, B)."""
    out = []
    for a in drugs:
        changers = set(a["inhibits"]) | set(a["induces"])
        for b in drugs:
            if a["name"] == b["name"]:
                continue
            common = sorted(changers & set(b["metabolism"]))
            if not common:
                continue
            how = []
            for enz in common:
                kinds = [k for k, sec in (("억제", "inhibits"), ("유도", "induces")) if enz in a[sec]]
                how.append(f"{enz}({'+'.join(kinds)})")
            out.append({"from": a["name"], "to": b["name"], "enzymes": common, "how": how})
    return out


def same_targets(drugs):
    """두 약의 actions 이름 교집합."""
    out = []
    for a, b in combinations(drugs, 2):
        for tgt in sorted(set(a["actions"]) & set(b["actions"])):
            ta, tb = a["actions"][tgt]["type"], b["actions"][tgt]["type"]
            if ta == tb == "agonist":
                label = "작용제끼리"
            elif ta == tb == "antagonist":
                label = "차단제끼리"
            else:
                label = "차단제 낌"
            out.append({"a": a["name"], "b": b["name"], "target": tgt,
                        "types": (ta, tb), "label": label})
    return out


def _direction(rule, tgt):
    dirs = [d for d in ("up", "down") if tgt in rule[d]]
    return "+".join(dirs)


def same_effects(drugs, rules):
    """서로 다른 대상이지만 규칙표에서 같은 효과로 이어지는 두 약."""
    out = []
    for a, b in combinations(drugs, 2):
        for eff, rule in rules["effects"].items():
            linked = set(rule["up"]) | set(rule["down"])
            for p in sorted(set(a["actions"]) & linked):
                for q in sorted(set(b["actions"]) & linked):
                    if p == q:
                        continue
                    dp, dq = _direction(rule, p), _direction(rule, q)
                    out.append({"a": a["name"], "b": b["name"], "effect": eff,
                                "target_a": p, "target_b": q, "dir_a": dp, "dir_b": dq,
                                "same_dir": dp == dq})
    return out


def classify(drugs, rules):
    return {
        "concentration": concentration_pairs(drugs),
        "same_target": same_targets(drugs),
        "same_effect": same_effects(drugs, rules),
    }


def format_classification(cls):
    parts = [
        format_table(
            ["바꾸는 약", "바뀌는 약", "겹친 효소"],
            [[c["from"], c["to"], ", ".join(c["how"])] for c in cls["concentration"]],
            "분류 1: 평균 농도를 바꾸는 순서쌍 (A → B)"),
        format_table(
            ["약 1", "약 2", "같은 대상", "종류"],
            [[s["a"], s["b"], s["target"],
              f"{s['label']} ({TYPE_KO[s['types'][0]]}·{TYPE_KO[s['types'][1]]})"]
             for s in cls["same_target"]],
            "분류 2: 같은 대상"),
        format_table(
            ["약 1", "약 2", "효과", "대상 1", "대상 2", "방향"],
            [[s["a"], s["b"], s["effect"], f"{s['target_a']}({s['dir_a']})",
              f"{s['target_b']}({s['dir_b']})", "같은 방향" if s["same_dir"] else "반대 방향"]
             for s in cls["same_effect"]],
            "분류 3: 서로 다른 대상, 같은 효과"),
    ]
    return "\n\n".join(parts)
