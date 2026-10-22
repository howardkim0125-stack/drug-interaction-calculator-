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
