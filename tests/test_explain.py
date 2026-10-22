import data_io
import run_demo
from data_io import DISCLAIMER
from tables import read_csv


def test_demo_runs_and_writes_outputs(tmp_path, capsys):
    res = run_demo.main(["--out", str(tmp_path)])
    text = capsys.readouterr().out
    assert DISCLAIMER in text
    for name in ("classification", "ratios", "effects"):
        path = tmp_path / f"demo_{name}.csv"
        lines = path.read_text(encoding="utf-8-sig").strip().splitlines()
        assert lines[-1] == f"# {DISCLAIMER}"
    report = (tmp_path / "demo_report.txt").read_text(encoding="utf-8").strip()
    assert report.endswith(DISCLAIMER)
    headers, rows = read_csv(tmp_path / "demo_effects.csv")
    assert len(rows) == len(res["effects"])
    assert "판정" in headers


def test_demo_subset(tmp_path, capsys):
    res = run_demo.main(["가상약A", "가상약B", "--out", str(tmp_path), "--prefix", "ab"])
    assert res["drugs"] == ["가상약A", "가상약B"]
    assert abs(res["ratios"]["가상약B"]["r"] - 2.8736) < 1e-3
    assert (tmp_path / "ab_effects.csv").exists()


def test_demo_data_is_virtual():
    for d in data_io.read_json(data_io.DATA_DIR / "drugs_demo.json")["drugs"]:
        for sec in ("metabolism", "inhibits", "induces", "actions"):
            for item in d.get(sec, {}).values():
                assert item["source"] == "virtual"
