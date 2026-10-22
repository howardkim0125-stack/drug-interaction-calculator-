import json

import pytest

import data_io
from data_io import DataError, DataWarning

ENZ = data_io.load_names()["enzymes"]


def drug(**kw):
    base = {"name": "X", "metabolism": {}, "inhibits": {}, "induces": {}, "actions": {}}
    base.update(kw)
    return base


def test_names_file():
    assert {"CYP3A", "CYP2C19", "CYP2D6", "CYP1A2", "CYP2C9"} <= ENZ


def test_full_example_parses():
    d = data_io.parse_drug({
        "name": "A",
        "metabolism": {"CYP3A": {"f": 0.7, "g": 0.5, "source": "virtual"}},
        "inhibits": {"CYP3A": {"s": 0.6, "t": 0.8, "source": "virtual"}},
        "induces": {"CYP2C19": {"u": 0.5, "source": "virtual"}},
        "actions": {"GABA_A": {"type": "agonist", "c": 0.43, "source": "virtual"}},
    }, ENZ)
    assert d["dose_ratio"] == 1.0
    assert d["metabolism"]["CYP3A"]["f"] == 0.7
    assert d["inhibits"]["CYP3A"]["t"] == 0.8
    assert d["actions"]["GABA_A"]["c"] == 0.43


def test_unknown_enzyme_is_error():
    raw = drug(metabolism={"CYP3A4": {"f": 0.5, "g": 0, "source": "virtual"}})
    with pytest.raises(DataError, match="허용되지 않은 효소"):
        data_io.parse_drug(raw, ENZ)
    raw = drug(inhibits={"FOO": {"s": 0.5, "t": 0, "source": "virtual"}})
    with pytest.raises(DataError):
        data_io.parse_drug(raw, ENZ)


def test_f_sum_over_one_is_error():
    raw = drug(metabolism={"CYP3A": {"f": 0.6, "g": 0, "source": "v"},
                           "CYP2D6": {"f": 0.5, "g": 0, "source": "v"}})
    with pytest.raises(DataError, match="f의 합"):
        data_io.parse_drug(raw, ENZ)


def test_ranges():
    with pytest.raises(DataError):
        data_io.parse_drug(drug(inhibits={"CYP3A": {"s": 1.0, "t": 0, "source": "v"}}), ENZ)
    with pytest.raises(DataError):
        data_io.parse_drug(drug(induces={"CYP3A": {"u": -0.1, "source": "v"}}), ENZ)
    with pytest.raises(DataError):
        data_io.parse_drug(drug(actions={"P": {"type": "agonist", "e": 1.0, "source": "v"}}), ENZ)
    with pytest.raises(DataError):
        data_io.parse_drug(drug(actions={"P": {"type": "partial", "c": 1, "source": "v"}}), ENZ)


def test_missing_source_is_error_and_empty_source_warns():
    with pytest.raises(DataError, match="source"):
        data_io.parse_drug(drug(induces={"CYP3A": {"u": 0.5}}), ENZ)
    with pytest.warns(DataWarning, match="출처"):
        data_io.parse_drug(drug(induces={"CYP3A": {"u": 0.5, "source": ""}}), ENZ)


def test_zero_element_warns():
    with pytest.warns(DataWarning, match="0인 원소"):
        data_io.parse_drug(drug(induces={"CYP3A": {"u": 0, "source": "v"}}), ENZ)
    with pytest.warns(DataWarning, match="0인 원소"):
        data_io.parse_drug(drug(metabolism={"CYP3A": {"f": 0, "g": 0, "source": "v"}}), ENZ)


def test_ki_and_e_conversion():
    d = data_io.parse_drug(drug(
        inhibits={"CYP3A": {"Ki": 2.0, "conc_liver": 2.0, "conc_gut": 6.0, "source": "v"}},
        actions={"P": {"type": "agonist", "e": 0.4, "source": "v"}}), ENZ)
    assert d["inhibits"]["CYP3A"]["s"] == pytest.approx(0.5)
    assert d["inhibits"]["CYP3A"]["t"] == pytest.approx(0.75)
    assert d["actions"]["P"]["c"] == pytest.approx(0.6667, abs=1e-3)


def test_e_on_antagonist_is_error():
    with pytest.raises(DataError, match="작용제"):
        data_io.parse_drug(drug(actions={"P": {"type": "antagonist", "e": 0.4, "source": "v"}}), ENZ)


def test_load_drugs_duplicate_name(tmp_path):
    p = tmp_path / "drugs_x.json"
    p.write_text(json.dumps({"drugs": [drug(), drug()]}), encoding="utf-8")
    with pytest.raises(DataError, match="중복"):
        data_io.load_drugs(p)


def test_real_template_is_blank():
    raw = data_io.read_json(data_io.DATA_DIR / "drugs_real_template.json")
    for d in raw["drugs"]:
        for sec in ("metabolism", "inhibits", "induces", "actions"):
            for item in d[sec].values():
                assert item["source"] == ""
                assert all(v is None for k, v in item.items() if k not in ("source", "type"))


def test_rules_file_and_defaults():
    with pytest.warns(DataWarning, match="출처"):
        rules = data_io.load_rules()
    assert rules["effects"]["sedation"]["k"] == 1.0
    r = data_io.parse_rules({"effects": {"X": {"up": ["P"], "source": "v"}}})
    assert r["effects"]["X"]["k"] == 1.0
    assert r["effects"]["X"]["threshold"] is None
    assert r["effects"]["X"]["down"] == []


def test_unknown_target_warns():
    rules = data_io.parse_rules({"effects": {"X": {"up": ["P"], "source": "v"}}})
    d = data_io.parse_drug(drug(actions={"Q": {"type": "agonist", "c": 1, "source": "v"}}), ENZ)
    with pytest.warns(DataWarning, match="Q"):
        data_io.check_targets([d], rules)


def test_config_defaults():
    cfg = data_io.load_config()
    assert cfg["judgement"]["b0_small"] == 0.05
    assert cfg["flag"]["r_high"] == 1.25
