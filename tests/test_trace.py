import pytest

import data_io
import interpret
import run_demo
import calc_trace
from data_io import DISCLAIMER

ENZ = data_io.load_names()["enzymes"]
CFG = data_io.load_config()


def check_values(drugs, rules):
    res = interpret.analyze(drugs, rules, CFG, check=False)
    text, values = calc_trace.build(drugs, rules, CFG, res)
    for e in res["effects"]:
        if e["involved"]:
            b0, br, bf = values[e["effect"]]
            assert b0 == pytest.approx(e["B0"], abs=1e-12)
            assert br == pytest.approx(e["Br"], abs=1e-12)
            assert bf == pytest.approx(e["Bfull"], abs=1e-12)
    assert text.strip().endswith(DISCLAIMER)
    return text


def test_trace_E2E_1_lines():
    a = data_io.parse_drug({"name": "A",
                            "inhibits": {"CYP3A": {"s": 0.6, "t": 0, "source": "v"}},
                            "actions": {"P": {"type": "agonist", "e": 0.3, "source": "v"}}}, ENZ)
    b = data_io.parse_drug({"name": "B",
                            "metabolism": {"CYP3A": {"f": 0.7, "g": 0, "source": "v"}},
                            "actions": {"P": {"type": "agonist", "e": 0.4, "source": "v"}}}, ENZ)
    rules = data_io.parse_rules({"effects": {"X": {"up": ["P"], "source": "v"}}})
    text = check_values([a, b], rules)
    assert "- r_간(B) = 1 ÷ (0.7 × 0.4 + 0.3) = 1.724" in text
    assert "- R = B_full ÷ B₀ = 0.6121 ÷ 0.5227 = 1.171" in text
    order = ["## 0.", "## 1. 분류", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "## 7. 발현"]
    pos = [text.index(h) for h in order]
    assert pos == sorted(pos)


def test_trace_E2E_2_synergy_line():
    a = data_io.parse_drug({"name": "A", "actions": {"P": {"type": "agonist", "c": 0.25, "source": "v"}}}, ENZ)
    b = data_io.parse_drug({"name": "B", "actions": {"Q": {"type": "agonist", "c": 0.25, "source": "v"}}}, ENZ)
    rules = data_io.parse_rules({"effects": {"Y": {"up": ["P", "Q"], "k": 4, "source": "v"}}})
    text = check_values([a, b], rules)
    assert "- c_합(up) = ((1 + 4 × 0.25) × (1 + 4 × 0.25) − 1) ÷ 4 = 0.75" in text


def test_trace_demo_values_and_file(tmp_path, capsys):
    drugs = data_io.load_drugs(data_io.DATA_DIR / "drugs_demo.json")
    rules = data_io.load_rules(data_io.DATA_DIR / "rules_demo.json")
    check_values(drugs, rules)
    run_demo.main(["--trace", "--out", str(tmp_path)])
    md = (tmp_path / "demo_trace.md").read_text(encoding="utf-8")
    assert md.startswith("# 계산 과정")
    assert "용량 2배" in md or "dose_ratio" in md
    assert capsys.readouterr().out.count("## ") >= 8


def test_trace_pk_and_ki_inputs():
    a = data_io.parse_drug({"name": "A", "dose_ratio": 2,
                            "inhibits": {"CYP3A": {"Ki": 1, "conc_liver": 1, "conc_gut": 3, "source": "v"}},
                            "actions": {"P": {"type": "agonist", "F": 0.5, "dose": 100, "CL": 10, "tau": 12,
                                              "EC50": 0.41667, "source": "v"}}}, ENZ)
    b = data_io.parse_drug({"name": "B", "metabolism": {"CYP3A": {"f": 0.5, "g": 0.2, "source": "v"}},
                            "actions": {"P": {"type": "antagonist", "c": 0.5, "source": "v"}}}, ENZ)
    rules = data_io.parse_rules({"effects": {"X": {"up": ["P"], "threshold": 0.5, "source": "v"}}})
    text = check_values([a, b], rules)
    assert "C(A) = F × dose ÷ (CL × tau) = 0.5 × 100 ÷ (10 × 12) = 0.4167" in text
    assert "x_간(A, CYP3A) = conc_liver ÷ Ki = 1 ÷ 1 = 1" in text
    assert "s(A, CYP3A, 용량 2배)" in text
