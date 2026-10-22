import ast
from itertools import combinations
from pathlib import Path

import pytest

import data_io
import interpret
from virtual import generator, truth

ROOT = Path(__file__).resolve().parent.parent
CFG = data_io.load_config()
CV = CFG["virtual"]
TOL = 1e-3


def mk(name, metabolism=None, inhibits=None, actions=None):
    return {"name": name, "dose_ratio": 1.0, "metabolism": metabolism or {},
            "inhibits": inhibits or {}, "induces": {}, "actions": actions or {}}


def rules_of(**effects):
    return data_io.parse_rules({"effects": {
        n: {"source": "virtual", **e} for n, e in effects.items()}})


def test_generator_reproducible():
    assert generator.generate_raw(3, CV) == generator.generate_raw(3, CV)
    assert generator.generate_raw(3, CV) != generator.generate_raw(4, CV)
    drugs, _ = generator.generate(0, CV, n_drugs=50)
    assert len(drugs) == 50


@pytest.mark.parametrize("seed", range(20))
def test_generator_ranges(seed):
    drugs, rules = generator.generate(seed, CV)
    assert len(drugs) == CV["n_drugs"]
    assert sorted(rules["effects"]) == ["E1", "E2", "E3", "E4"]
    for eff in rules["effects"].values():
        assert 1 <= len(eff["up"]) <= 3 and len(eff["down"]) <= 1
        assert not set(eff["up"]) & set(eff["down"])
        assert 0 <= eff["k"] <= 4
        assert eff["threshold"] is None or 0.3 <= eff["threshold"] <= 0.8
    for d in drugs:
        assert 1 <= len(d["metabolism"]) <= 3
        assert 0.5 - 1e-9 <= sum(m["f"] for m in d["metabolism"].values()) <= 1 + 1e-9
        for enz, m in d["metabolism"].items():
            assert enz in CV["enzymes"]
            assert m["g"] == 0 or (enz == "CYP3A" and m["g"] <= 0.6)
        assert len(d["inhibits"]) <= 1 and len(d["induces"]) <= 1
        for i in d["inhibits"].values():
            assert 0.2 <= i["s"] <= 0.9 and i["s"] <= i["t"] <= 0.95
        for i in d["induces"].values():
            assert 0.2 <= i["u"] <= 1.5
        assert 1 <= len(d["actions"]) <= 2
        for a in d["actions"].values():
            assert 0.1 <= a["c"] <= 3


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_truth_all_off_equals_system(seed):
    drugs, rules = generator.generate(seed, CV)
    world = truth.TruthWorld(drugs, rules, truth.all_off(CFG["truth"]), seed)
    combos = list(combinations(drugs, 2)) + list(combinations(drugs[:6], 3))
    for combo in combos:
        sys = interpret.analyze(list(combo), rules, CFG, check=False)
        tru = world.evaluate([d["name"] for d in combo])
        for n in tru["r"]:
            assert tru["r"][n] == pytest.approx(sys["ratios"][n]["r"], abs=1e-9)
        for e in sys["effects"]:
            assert tru["Bfull"][e["effect"]] == pytest.approx(e["Bfull"], abs=1e-9)
            assert tru["B0"][e["effect"]] == pytest.approx(e["B0"], abs=1e-9)


def test_transporter():
    st = truth.with_strength(truth.all_off(CFG["truth"]), "transporter", 0.3)
    st["transporter"]["p"] = 1.0
    a = mk("A", inhibits={"CYP3A": {"s": 0.6, "t": 0.0}})
    b = mk("B", metabolism={"CYP3A": {"f": 0.7, "g": 0.0}})
    world = truth.TruthWorld([a, b], rules_of(X={"up": ["P"]}), st, 0)
    r = world.evaluate(["A", "B"])["r"]
    assert r["B"] == pytest.approx(1.7241 * 1.3, abs=TOL)
    assert r["A"] == pytest.approx(1.3, abs=TOL)   # 효소 교집합이 없는 쌍도 1 + m


def test_partial_agonist():
    st = truth.with_strength(truth.all_off(CFG["truth"]), "partial_agonist", 1.0)
    a = mk("A", actions={"P": {"type": "agonist", "c": 1.0}})
    world = truth.TruthWorld([a], rules_of(X={"up": ["P"]}), st, 0)
    emax = world.emax("A", "P")
    assert 0.5 <= emax <= 0.9
    assert world.evaluate(["A"])["Bfull"]["X"] == pytest.approx(emax * 0.5, abs=1e-9)


def test_cascade_mutual_inhibition():
    # A, B가 서로의 분해 효소를 s = 0.5로 억제, f = 0.8
    a = mk("A", metabolism={"CYP2D6": {"f": 0.8, "g": 0.0}}, inhibits={"CYP3A": {"s": 0.5, "t": 0.0}})
    b = mk("B", metabolism={"CYP3A": {"f": 0.8, "g": 0.0}}, inhibits={"CYP2D6": {"s": 0.5, "t": 0.0}})
    rules = rules_of(X={"up": ["P"]})
    off = truth.TruthWorld([a, b], rules, truth.all_off(CFG["truth"]), 0)
    assert off.evaluate(["A", "B"])["r"]["B"] == pytest.approx(1 / 0.6, abs=TOL)
    on = truth.TruthWorld([a, b], rules, truth.with_strength(truth.all_off(CFG["truth"]), "cascade", 1), 0)
    res = on.evaluate(["A", "B"])
    assert res["converged"]
    # 고정점: r = 1 ÷ (0.8 ÷ (1 + r) + 0.2) → 0.2r² = 1 → r = √5
    assert res["r"]["B"] == pytest.approx(5 ** 0.5, abs=TOL)


def test_k_error_and_noise_bounds():
    drugs, rules = generator.generate(0, CV)
    st = truth.with_strength(truth.all_off(CFG["truth"]), "k_error", 0.2)
    world = truth.TruthWorld(drugs, rules, st, 0)
    for eff, rule in rules["effects"].items():
        assert rule["k"] * 0.8 - 1e-12 <= world.true_k(eff) <= rule["k"] * 1.2 + 1e-12
    st = truth.with_strength(truth.all_off(CFG["truth"]), "noise", 0.02)
    world = truth.TruthWorld(drugs, rules, st, 0)
    res = world.evaluate([drugs[0]["name"], drugs[1]["name"]])
    for eff in rules["effects"]:
        assert abs(res["Bfull"][eff] - res["Bfull_clean"][eff]) <= 0.02


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def test_system_never_imports_truth():
    for f in ("data_io.py", "model.py", "classify.py", "interpret.py", "explain.py",
              "tables.py", "run_demo.py"):
        assert not any("truth" in n for n in _imports(ROOT / f)), f


def test_truth_does_not_use_system_formulas():
    assert not _imports(ROOT / "virtual" / "truth.py") & {"model", "interpret", "classify"}
