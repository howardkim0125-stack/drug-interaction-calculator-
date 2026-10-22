import pytest

from real import compare

TOL = 1e-3
HEAD = ",".join(compare.COLUMNS)


def write(tmp_path, lines):
    p = tmp_path / "pairs.csv"
    p.write_text("\n".join([HEAD, *lines]) + "\n", encoding="utf-8")
    return p


def test_template_has_no_numbers():
    rows, skipped = compare.read_pairs(compare.data_io.DATA_DIR / "real_pairs_template.csv")
    assert rows == [] and len(skipped) == 2


def test_grade_edges():
    assert compare.grade(1.2) == "1.25배 미만"
    assert compare.grade(1.25) == "1.25~2배"
    assert compare.grade(2.0) == "2~5배"
    assert compare.grade(5.0) == "5배 이상"


def test_calibrate_and_predict(tmp_path):
    # 시험용 가상 숫자: 보정 쌍에서 s = 0.6 (T11), 검증 쌍 f = 0.8, g = 0
    p = write(tmp_path, [
        "S1,I,CYP3A,0.7,v,0.5,v,100,2.46305,v,보정",
        "S2,I,CYP3A,0.8,v,0,v,100,1.9,v,검증",
        "S3,I,CYP3A,0.8,v,0,v,200,2.0,v,검증",
        "S4,J,CYP3A,0.8,v,0,v,100,2.0,v,검증",
    ])
    rows, skipped = compare.read_pairs(p)
    calib, failed = compare.calibrate(rows)
    assert calib[("I", "CYP3A")][0]["s"] == pytest.approx(0.6, abs=TOL)
    res, unmatched = compare.compare(rows, calib)
    assert len(unmatched) == 1                        # J는 보정 결과 없음
    same, double = res
    assert same["예측_r"] == pytest.approx(1 / (1 - 0.8 * 0.6), abs=TOL)
    assert same["상대오차"] == pytest.approx((1 / 0.52 - 1.9) / 1.9, abs=TOL)
    assert same["등급_일치"]
    # 용량 2배: x = 1.5 × 2 = 3 → s = 0.75
    assert double["s"] == pytest.approx(0.75, abs=TOL)
    assert double["예측_r"] == pytest.approx(2.5, abs=TOL)


def test_multiple_calibrations_average_s(tmp_path):
    p = write(tmp_path, [
        "S1,I,CYP3A,0.7,v,0,v,100,1.7241379,v,보정",   # s = 0.6
        "S2,I,CYP3A,0.5,v,0,v,100,1.25,v,보정",        # s = 0.4
        "S3,I,CYP3A,1.0,v,0,v,100,2.0,v,검증",
    ])
    rows, _ = compare.read_pairs(p)
    res, _ = compare.compare(rows, compare.calibrate(rows)[0])
    assert res[0]["s"] == pytest.approx(0.5, abs=TOL)
    assert res[0]["예측_r"] == pytest.approx(2.0, abs=TOL)


def test_calibration_without_root_is_reported(tmp_path):
    p = write(tmp_path, ["S1,I,CYP3A,0.3,v,0,v,100,10,v,보정"])
    rows, _ = compare.read_pairs(p)
    calib, failed = compare.calibrate(rows)
    assert calib == {} and len(failed) == 1


def test_bad_enzyme_is_error(tmp_path):
    p = write(tmp_path, ["S1,I,CYP3A4,0.7,v,0,v,100,2,v,보정"])
    with pytest.raises(compare.data_io.DataError):
        compare.read_pairs(p)


def test_run_template(tmp_path, capsys):
    compare.main(["--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert "건너뛴 행 2개" in out and compare.DISCLAIMER in out
