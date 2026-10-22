"""실제 약 비교 (명세 7).

1. 보정용 쌍에서 3-7의 역산으로 억제 정도 s(= t)를 구한다.
2. 같은 억제제·효소의 검증용 쌍에서 r을 예측한다.
   - 보정 용량과 검증 용량이 다르면 x = s ÷ (1 − s)를 (검증 용량 ÷ 보정 용량)배 해서 환산한다.
   - 보정용 쌍이 여러 개면 검증 용량으로 환산한 s들의 산술평균을 쓴다.
3. 보고된 AUC 비와 비교해 상대오차와 등급 일치를 계산한다(등급 경계 1.25, 2, 5배).

사용: python -m real.compare [CSV 경로]   (기본: data/real_pairs_template.csv)
"""
import argparse
import csv
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import data_io  # noqa: E402
import model  # noqa: E402
from data_io import DISCLAIMER  # noqa: E402
from tables import format_table, write_csv  # noqa: E402

COLUMNS = ["기질", "억제제", "효소", "f", "f_출처", "g", "g_출처", "억제제_용량",
           "보고된_AUC_비", "AUC_비_출처", "용도"]
NUMERIC = ["f", "g", "억제제_용량", "보고된_AUC_비"]
GRADE_EDGES = (1.25, 2.0, 5.0)
GRADE_NAMES = ("1.25배 미만", "1.25~2배", "2~5배", "5배 이상")


def grade(R):
    for edge, name in zip(GRADE_EDGES, GRADE_NAMES):
        if R < edge:
            return name
    return GRADE_NAMES[-1]


def read_pairs(path, enzymes=None):
    """CSV를 읽어 채워진 행과 건너뛴 행(이유)을 나눈다."""
    if enzymes is None:
        enzymes = data_io.load_names()["enzymes"]
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise data_io.DataError(f"{path}: 열이 없다 {missing}")
        raw = [row for row in reader if any((v or "").strip() for v in row.values())
               and not (row.get("기질") or "").startswith("#")]

    rows, skipped = [], []
    for i, row in enumerate(raw, start=2):
        row = {k: (v or "").strip() for k, v in row.items()}
        blank = [c for c in ["기질", "억제제", "효소", *NUMERIC, "용도"] if not row[c]]
        if blank:
            skipped.append((i, f"빈칸 {blank}"))
            continue
        try:
            vals = {c: float(row[c]) for c in NUMERIC}
        except ValueError:
            skipped.append((i, "숫자 칸에 숫자가 아닌 값"))
            continue
        if row["효소"] not in enzymes:
            raise data_io.DataError(f"{path} {i}행: 허용되지 않은 효소 이름 '{row['효소']}'")
        if row["용도"] not in ("보정", "검증"):
            raise data_io.DataError(f"{path} {i}행: 용도는 '보정' 또는 '검증'이어야 한다")
        if not (0 <= vals["f"] <= 1 and 0 <= vals["g"] <= 1):
            raise data_io.DataError(f"{path} {i}행: f, g는 0 이상 1 이하여야 한다")
        if vals["억제제_용량"] <= 0 or vals["보고된_AUC_비"] <= 0:
            raise data_io.DataError(f"{path} {i}행: 용량과 AUC 비는 0보다 커야 한다")
        for c in ("f_출처", "g_출처", "AUC_비_출처"):
            if not row[c]:
                warnings.warn(f"{path} {i}행: {c}가 비어 있다", data_io.DataWarning, stacklevel=2)
        rows.append({**row, **vals, "line": i})
    return rows, skipped


def calibrate(rows):
    """보정용 쌍마다 역산한 s. 키는 (억제제, 효소)."""
    calib, failed = {}, []
    for row in rows:
        if row["용도"] != "보정":
            continue
        try:
            s = model.invert_inhibition(row["f"], row["g"], row["보고된_AUC_비"])
        except ValueError as exc:
            failed.append((row["line"], str(exc)))
            continue
        calib.setdefault((row["억제제"], row["효소"]), []).append(
            {"s": s, "dose": row["억제제_용량"], "line": row["line"], "기질": row["기질"]})
    return calib, failed


def predict_r(f, g, s):
    """s = t로 두고 r = r_간 × r_장."""
    return model.r_from_fractions([(f, 1 - s)]) * model.r_from_fractions([(g, 1 - s)])


def compare(rows, calib):
    results, unmatched = [], []
    for row in rows:
        if row["용도"] != "검증":
            continue
        cal = calib.get((row["억제제"], row["효소"]))
        if not cal:
            unmatched.append((row["line"], f"같은 억제제·효소({row['억제제']}, {row['효소']})의 보정 결과가 없다"))
            continue
        scaled = [model.scale_inhibition(c["s"], row["억제제_용량"] / c["dose"]) for c in cal]
        s = sum(scaled) / len(scaled)
        r_pred = predict_r(row["f"], row["g"], s)
        R = row["보고된_AUC_비"]
        g_pred, g_rep = grade(r_pred), grade(R)
        results.append({
            "line": row["line"], "기질": row["기질"], "억제제": row["억제제"], "효소": row["효소"],
            "f": row["f"], "g": row["g"], "용량": row["억제제_용량"],
            "보정_s": [c["s"] for c in cal], "보정_행": [c["line"] for c in cal], "s": s,
            "예측_r": r_pred, "보고_AUC_비": R, "상대오차": (r_pred - R) / R,
            "예측_등급": g_pred, "보고_등급": g_rep, "등급_일치": g_pred == g_rep,
        })
    return results, unmatched


def run(path, out_dir):
    rows, skipped = read_pairs(path)
    calib, failed = calibrate(rows)
    results, unmatched = compare(rows, calib)

    print(f"파일: {path}")
    print(f"채워진 행 {len(rows)}개 (보정 {sum(r['용도'] == '보정' for r in rows)}, "
          f"검증 {sum(r['용도'] == '검증' for r in rows)}), 건너뛴 행 {len(skipped)}개")
    for line, why in skipped + failed + unmatched:
        print(f"  {line}행 건너뜀: {why}")

    cal_rows = [[c["line"], inh, enz, c["기질"], c["dose"], c["s"]]
                for (inh, enz), items in calib.items() for c in items]
    print()
    print(format_table(["행", "억제제", "효소", "기질", "용량", "역산 s"], cal_rows, "보정: 역산한 억제 정도"))

    headers = ["행", "기질", "억제제", "효소", "f", "g", "용량", "s(환산 평균)", "예측 r",
               "보고 AUC 비", "상대오차", "예측 등급", "보고 등급", "등급 일치"]
    res_rows = [[r["line"], r["기질"], r["억제제"], r["효소"], r["f"], r["g"], r["용량"], r["s"],
                 r["예측_r"], r["보고_AUC_비"], r["상대오차"], r["예측_등급"], r["보고_등급"],
                 "일치" if r["등급_일치"] else "불일치"] for r in results]
    print()
    print(format_table(headers, res_rows, "검증: 예측과 보고값 비교"))
    if results:
        mae = sum(abs(r["상대오차"]) for r in results) / len(results)
        agree = sum(r["등급_일치"] for r in results) / len(results)
        print(f"\n평균 |상대오차| = {mae:.4f}, 등급 일치율 = {agree:.4f} ({len(results)}쌍)")
    print("\n" + DISCLAIMER)

    out = write_csv(Path(out_dir) / "real_compare.csv", headers, res_rows)
    print(f"저장: {out}")
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="실제 약 쌍 비교")
    ap.add_argument("path", nargs="?", default=str(data_io.DATA_DIR / "real_pairs_template.csv"))
    ap.add_argument("--out", default=str(data_io.OUT_DIR))
    args = ap.parse_args(argv)
    return run(args.path, args.out)


if __name__ == "__main__":
    main()
