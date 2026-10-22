import json
import math

import pytest

import data_io
import evaluate
import run_eval
from virtual import truth

CFG = data_io.load_config()


def test_all_factors_off_is_perfect():
    res = evaluate.evaluate_world(0, CFG, truth.all_off(CFG["truth"]), n_drugs=10, triples=20)
    m = res["metrics"]
    assert res["n_combos"] == 45 + 20
    for key in ("mech_precision", "mech_recall", "mech_accuracy", "judge_accuracy",
                "verdict_agreement"):
        assert m[key] == pytest.approx(1.0)
    assert m["mae_r"] < 1e-9 and m["mae_effect"] < 1e-9
    for key in ("manifest_precision", "manifest_recall", "judge_precision", "judge_recall"):
        assert math.isnan(m[key]) or m[key] == pytest.approx(1.0)


def test_hidden_transporter_lowers_mechanism_recall_only():
    st = truth.with_strength(truth.all_off(CFG["truth"]), "transporter", 0.2)
    res = evaluate.evaluate_world(0, CFG, st, n_drugs=10)
    m = res["metrics"]
    assert m["mech_precision"] == pytest.approx(1.0)
    assert m["mech_recall"] < 1.0
    c = res["counts"]["mech"]
    assert c["tp"] + c["fp"] + c["fn"] + c["tn"] == 10 * 9


def test_stress_and_summary():
    runs = evaluate.stress(CFG, factors=("noise", "cascade"), seeds=[0, 1],
                           strengths=[0, 0.2], n_drugs=6, triples=0)
    assert len(runs) == 2 * 2 + 2 * 2
    head, rows = evaluate.summarize(runs)
    assert head[:3] == ["factor", "strength", "metric"]
    assert len(rows) == 4 * len(evaluate.METRICS)
    zero = {r[2]: r for r in rows if r[0] == "noise" and r[1] == 0}
    assert zero["mae_effect"][3] < 1e-9
    assert zero["verdict_agreement"][4] == pytest.approx(1.0)


def test_run_log(tmp_path):
    path = tmp_path / "run_log.json"
    run_eval.log_run({"mode": "test", "seeds": [1, 2]}, path)
    run_eval.log_run({"mode": "test2", "seeds": [3]}, path)
    log = json.loads(path.read_text(encoding="utf-8"))
    assert [e["mode"] for e in log] == ["test", "test2"]
    assert log[0]["seeds"] == [1, 2] and "date" in log[0]


def test_run_eval_writes_files(tmp_path, capsys):
    run_eval.main(["--n-drugs", "8", "--out", str(tmp_path)])
    for name in ("eval_metrics", "eval_counts", "eval_confusion", "eval_pairs", "eval_effects"):
        assert (tmp_path / f"{name}.csv").exists()
    assert (tmp_path / "run_log.json").exists()
    assert data_io.DISCLAIMER in capsys.readouterr().out


def _fake_sys(singles, r, threshold=None):
    rule = {"up": ["P"], "down": [], "k": 1.0, "threshold": threshold, "source": "v"}
    return {"drugs": list(singles), "ratios": {n: {"r": r[n]} for n in singles},
            "classification": {"concentration": [{"from": "A", "to": "B"}]},
            "effects": [{"effect": "X", "rule": rule, "involved": list(singles), "singles": singles,
                         "B0": 0.5, "Bfull": 0.6}]}


def test_comparison_model_formulas():
    sys = _fake_sys({"A": 0.4, "B": 0.5}, {"A": 1.0, "B": 2.0})
    m1 = evaluate.predict(sys, "simple_sum", CFG)
    assert m1["r"] == {"A": 1.0, "B": 1.0} and m1["pairs"] == set()
    assert m1["effects"][0]["Bfull"] == pytest.approx(0.9)
    assert m1["effects"][0]["verdict"] == "독립"          # 자기 기준값(r = 1)과 같음
    m2 = evaluate.predict(sys, "proportional", CFG)
    assert m2["effects"][0]["Bfull"] == pytest.approx(1.0)   # 0.4 + 2 × 0.5 = 1.4 → 1로 자름
    assert m2["effects"][0]["B0"] == pytest.approx(0.9)
    assert m2["effects"][0]["verdict"] == "증강"
    assert m2["pairs"] == {("A", "B")}
    neg = evaluate.predict(_fake_sys({"A": -0.8, "B": -0.7}, {"A": 1, "B": 1}), "simple_sum", CFG)
    assert neg["effects"][0]["Bfull"] == pytest.approx(-1.0)
    sysm = evaluate.predict(sys, "system", CFG)
    assert sysm["effects"][0]["Bfull"] == 0.6


def test_compare_models_and_sensitivity():
    worlds = [evaluate.build_world(s, CFG, CFG["truth"], 8, 10) for s in (0, 1)]
    runs = evaluate.compare_models(worlds, CFG)
    assert len(runs) == 2 * 3
    m1 = [r for r in runs if r["model"] == "simple_sum"]
    assert all(r["mech_recall"] == 0 and math.isnan(r["mech_precision"]) for r in m1)
    sens = evaluate.sensitivity(worlds, CFG, [(1.03, 0.97), (1.10, 0.90)])
    assert {r["thresholds"] for r in sens} == {"1.03/0.97", "1.1/0.9"}
    c2 = evaluate.with_ratio_thresholds(CFG, 1.1, 0.9)
    assert c2["judgement"]["ratio_up"] == 1.1 and CFG["judgement"]["ratio_up"] == 1.05


def test_basic_eval_includes_triples(tmp_path, capsys):
    res = run_eval.main(["--n-drugs", "8", "--out", str(tmp_path)])
    assert res["n_combos"] == 28 + 56          # 2약 28개 + 3약 C(8,3) = 56개(200개보다 적음)
    res = run_eval.main(["--n-drugs", "8", "--no-triples", "--out", str(tmp_path)])
    assert res["n_combos"] == 28


def test_run_compare_writes_files(tmp_path, capsys):
    cfg = data_io.load_config()
    cfg["evaluate"]["multi"] = {"seeds": [0, 1], "n_drugs": 6, "triples": 5}
    out = run_eval.run_compare_and_sensitivity(cfg, tmp_path)
    for name in ("compare_models.csv", "compare_models_runs.csv", "compare_models.png",
                 "sensitivity.csv", "sensitivity_runs.csv"):
        assert (tmp_path / name).exists()
    assert {row[0] for row in out["sensitivity"]} == {"1.03/0.97", "1.05/0.95", "1.1/0.9"}
