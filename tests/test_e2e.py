import pytest

import data_io
import interpret

TOL = 1e-3
ENZ = data_io.load_names()["enzymes"]
CFG = data_io.load_config()


def approx(x):
    return pytest.approx(x, abs=TOL)


def effect(res, name):
    return next(e for e in res["effects"] if e["effect"] == name)


def test_E2E_1_enzyme_interaction():
    a = data_io.parse_drug({
        "name": "A",
        "inhibits": {"CYP3A": {"s": 0.6, "t": 0, "source": "virtual"}},
        "actions": {"P": {"type": "agonist", "e": 0.3, "source": "virtual"}},
    }, ENZ)
    b = data_io.parse_drug({
        "name": "B",
        "metabolism": {"CYP3A": {"f": 0.7, "g": 0, "source": "virtual"}},
        "actions": {"P": {"type": "agonist", "e": 0.4, "source": "virtual"}},
    }, ENZ)
    rules = data_io.parse_rules({"effects": {"X": {"up": ["P"], "source": "virtual"}}})
    res = interpret.analyze([a, b], rules, CFG)

    assert res["ratios"]["B"]["r"] == approx(1.7241)
    assert res["ratios"]["A"]["r"] == approx(1.0)
    x = effect(res, "X")
    assert x["B0"] == approx(0.5227)
    assert x["Bfull"] == approx(0.6121)
    assert x["R"] == approx(1.171)
    assert x["verdict"] == "증강"
    assert x["cause"] == "r"
    assert x["k_contrib"] == approx(0)

    cls = res["classification"]
    assert [(c["from"], c["to"]) for c in cls["concentration"]] == [("A", "B")]
    assert [(s["target"], s["label"]) for s in cls["same_target"]] == [("P", "작용제끼리")]


def test_E2E_2_target_synergy():
    a = data_io.parse_drug({"name": "A", "actions": {
        "P": {"type": "agonist", "c": 0.25, "source": "virtual"}}}, ENZ)
    b = data_io.parse_drug({"name": "B", "actions": {
        "Q": {"type": "agonist", "c": 0.25, "source": "virtual"}}}, ENZ)
    rules = data_io.parse_rules({"effects": {"Y": {"up": ["P", "Q"], "k": 4, "source": "virtual"}}})
    res = interpret.analyze([a, b], rules, CFG)

    y = effect(res, "Y")
    assert y["B0"] == approx(0.36)
    assert y["Bfull"] == approx(0.4286)
    assert y["R"] == approx(1.190)
    assert y["verdict"] == "증강"
    assert y["cause"] == "k"
    assert y["r_contrib"] == approx(0)

    cls = res["classification"]
    assert cls["concentration"] == []
    assert [(s["target_a"], s["target_b"]) for s in cls["same_effect"]] == [("P", "Q")]


def test_judge_small_b0_follows_b0_direction():
    # |B₀| < 0.05: d = (B_full − B₀) × sign(B₀)
    assert interpret.judge(-0.04, -0.20, CFG)[0] == "증강"
    assert interpret.judge(0.04, -0.20, CFG)[0] == "감소"
    assert interpret.judge(0.0, 0.03, CFG)[0] == "독립"
    # |B₀| ≥ 0.05: R = B_full ÷ B₀, 음수끼리면 크기 비율
    assert interpret.judge(-0.2, -0.3, CFG)[0] == "증강"
    assert interpret.judge(0.2, -0.1, CFG)[0] == "감소"
    assert interpret.judge(0.2, 0.205, CFG)[0] == "독립"


def test_cause_label_threshold():
    assert interpret.cause_label("증강", 0.06, 0.07, CFG) == "r+k"
    assert interpret.cause_label("증강", 0.01, 0.07, CFG) == "k"
    assert interpret.cause_label("증강", 0.01, 0.02, CFG) == "없음"
    assert interpret.cause_label("독립", 0.06, 0.07, CFG) == "-"


def test_manifestation():
    a = data_io.parse_drug({"name": "A", "actions": {
        "P": {"type": "agonist", "c": 0.25, "source": "virtual"}}}, ENZ)
    b = data_io.parse_drug({"name": "B", "actions": {
        "Q": {"type": "agonist", "c": 0.25, "source": "virtual"}}}, ENZ)
    # 단독 0.2씩, B₀ = 0.36, B_full = 0.4286
    for thr, shown, kind in [(0.4, True, "상호작용 때문에 발현"),
                             (0.3, True, "더하기만으로 발현"),
                             (0.45, False, "기준 미만"),
                             (0.15, False, "단독으로 이미 기준 이상(A, B)")]:
        rules = data_io.parse_rules({"effects": {"Y": {
            "up": ["P", "Q"], "k": 4, "threshold": thr, "source": "virtual"}}})
        y = effect(interpret.analyze([a, b], rules, CFG), "Y")
        assert (y["manifest"], y["manifest_kind"]) == (shown, kind)


def test_r_flag():
    assert interpret.r_flag(1.25, CFG) == "평균 농도 증가"
    assert interpret.r_flag(0.8, CFG) == "평균 농도 감소"
    assert interpret.r_flag(1.1, CFG) is None
