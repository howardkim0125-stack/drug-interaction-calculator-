"""사람이 읽는 표와 CSV 쓰기."""
import csv
import unicodedata
from pathlib import Path

from data_io import DISCLAIMER


def _width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text, width):
    return text + " " * (width - _width(text))


def fmt(v, nd=4):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def format_table(headers, rows, title=None):
    cells = [[fmt(c) for c in row] for row in rows]
    widths = [_width(h) for h in headers]
    for row in cells:
        for i, c in enumerate(row):
            widths[i] = max(widths[i], _width(c))
    line = "  ".join("-" * w for w in widths)
    out = []
    if title:
        out.append(f"[{title}]")
    out.append("  ".join(_pad(h, w) for h, w in zip(headers, widths)))
    out.append(line)
    if not cells:
        out.append("(없음)")
    for row in cells:
        out.append("  ".join(_pad(c, w) for c, w in zip(row, widths)))
    return "\n".join(out)


def write_csv(path, headers, rows, disclaimer=True):
    """CSV를 쓴다. 마지막 줄에 면책 문구를 붙인다(# 로 시작)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        for row in rows:
            w.writerow(["" if c is None else c for c in row])
        if disclaimer:
            w.writerow([f"# {DISCLAIMER}"])
    return path


def read_csv(path):
    """write_csv로 쓴 파일을 읽는다(# 줄은 건너뜀)."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r and not r[0].startswith("#")]
    return rows[0], rows[1:]
