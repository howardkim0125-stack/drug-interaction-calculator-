"""가상 약과 가상 규칙표 생성 (명세 6-1). 같은 seed면 같은 결과."""
import json
import random
from pathlib import Path

import data_io

SOURCE = "virtual"


def _u(rng, lo_hi):
    lo, hi = lo_hi
    return rng.uniform(lo, hi)


def _count(rng, lo_hi):
    lo, hi = lo_hi
    return rng.randint(lo, hi)


def target_names(cfg_v):
    return [f"T{i + 1}" for i in range(cfg_v["n_targets"])]


def effect_names(cfg_v):
    return [f"E{i + 1}" for i in range(cfg_v["n_effects"])]


def make_drug(rng, name, cfg_v):
    enzymes = cfg_v["enzymes"]
    targets = target_names(cfg_v)

    met_enz = rng.sample(enzymes, _count(rng, cfg_v["metabolism_count"]))
    f_total = _u(rng, cfg_v["f_total"])
    weights = [1.0 - rng.random() for _ in met_enz]
    metabolism = {}
    for enz, w in zip(met_enz, weights):
        g = _u(rng, cfg_v["g_cyp3a"]) if enz == "CYP3A" else 0.0
        metabolism[enz] = {"f": f_total * w / sum(weights), "g": g, "source": SOURCE}

    inhibits = {}
    if rng.random() < cfg_v["p_inhibit"]:
        enz = rng.choice(enzymes)
        s = _u(rng, cfg_v["s"])
        t = rng.uniform(s, cfg_v["t_max"])
        inhibits[enz] = {"s": s, "t": t, "source": SOURCE}

    induces = {}
    if rng.random() < cfg_v["p_induce"]:
        enz = rng.choice(enzymes)
        induces[enz] = {"u": _u(rng, cfg_v["u"]), "source": SOURCE}

    actions = {}
    for tgt in rng.sample(targets, _count(rng, cfg_v["action_count"])):
        typ = "antagonist" if rng.random() < cfg_v["p_antagonist"] else "agonist"
        actions[tgt] = {"type": typ, "c": _u(rng, cfg_v["c"]), "source": SOURCE}

    return {"name": name, "metabolism": metabolism, "inhibits": inhibits,
            "induces": induces, "actions": actions}


def make_rules(rng, cfg_v):
    targets = target_names(cfg_v)
    effects = {}
    for eff in effect_names(cfg_v):
        up = rng.sample(targets, _count(rng, cfg_v["up_count"]))
        rest = [t for t in targets if t not in up]
        down = rng.sample(rest, min(len(rest), _count(rng, cfg_v["down_count"])))
        k = _u(rng, cfg_v["k"]) if rng.random() < cfg_v["p_k_not_one"] else 1.0
        thr = _u(rng, cfg_v["threshold"]) if rng.random() < cfg_v["p_threshold"] else None
        effects[eff] = {"up": up, "down": down, "k": k, "threshold": thr, "source": SOURCE}
    return {"effects": effects}


def generate_raw(seed, cfg_v, n_drugs=None):
    """JSON 형태(파일에 쓰는 형태) 그대로의 가상 약 목록과 규칙표."""
    n = cfg_v["n_drugs"] if n_drugs is None else n_drugs
    rng = random.Random(seed)
    rules = make_rules(rng, cfg_v)
    width = len(str(n))
    drugs = [make_drug(rng, f"V{i + 1:0{width}d}", cfg_v) for i in range(n)]
    return drugs, rules


def generate(seed, cfg_v, n_drugs=None):
    """검사를 거친 계산용 형태의 가상 약 목록과 규칙표."""
    raw_drugs, raw_rules = generate_raw(seed, cfg_v, n_drugs)
    names = data_io.load_names()
    drugs = [data_io.parse_drug(d, names["enzymes"]) for d in raw_drugs]
    return drugs, data_io.parse_rules(raw_rules)


def save(seed, cfg_v, out_dir, n_drugs=None):
    raw_drugs, raw_rules = generate_raw(seed, cfg_v, n_drugs)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = len(raw_drugs)
    pd = out_dir / f"drugs_virtual_seed{seed}_n{n}.json"
    pr = out_dir / f"rules_virtual_seed{seed}_n{n}.json"
    pd.write_text(json.dumps({"drugs": raw_drugs}, ensure_ascii=False, indent=1), encoding="utf-8")
    pr.write_text(json.dumps(raw_rules, ensure_ascii=False, indent=1), encoding="utf-8")
    return pd, pr
