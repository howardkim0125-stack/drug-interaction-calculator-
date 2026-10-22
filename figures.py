"""보고서용 그래프 7개 (한국어, PNG 200dpi).

사용: python figures.py [--out 폴더]   (기본: out/figures)
"""
import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import model  # noqa: E402
from data_io import DISCLAIMER, OUT_DIR  # noqa: E402
from plotstyle import (BLUE, ORANGE, ORDINAL_3, ORDINAL_4, REFERENCE, SURFACE,  # noqa: E402
                       TEXT_PRIMARY, TEXT_SECONDARY, setup_font, style_axes)

DPI = 200


def new_fig(title):
    fig, ax = plt.subplots(figsize=(7.5, 5.2), facecolor=SURFACE)
    style_axes(ax, grid_axis="both")
    ax.set_title(title, color=TEXT_PRIMARY, fontsize=13, loc="left", pad=12)
    return fig, ax


def finish(fig, ax, path, xlabel, ylabel):
    ax.set_xlabel(xlabel, color=TEXT_SECONDARY, fontsize=11)
    ax.set_ylabel(ylabel, color=TEXT_SECONDARY, fontsize=11)
    fig.text(0.01, 0.01, DISCLAIMER, color=TEXT_SECONDARY, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)
    return path


def label(ax, x, y, text, color=TEXT_SECONDARY, **kw):
    ax.annotate(text, (x, y), color=color, fontsize=10, **kw)


def point(ax, x, y, text, dx=8, dy=-14, color=TEXT_PRIMARY):
    ax.plot([x], [y], marker="o", markersize=7, color=color, markeredgecolor=SURFACE,
            markeredgewidth=1.5, zorder=5)
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", color=TEXT_PRIMARY, fontsize=10)


def point_arrow(ax, x, y, text, tx, ty):
    ax.plot([x], [y], marker="o", markersize=7, color=TEXT_PRIMARY, markeredgecolor=SURFACE,
            markeredgewidth=1.5, zorder=5)
    ax.annotate(text, (x, y), xytext=(tx, ty), color=TEXT_PRIMARY, fontsize=10,
                arrowprops={"arrowstyle": "-", "color": TEXT_SECONDARY, "linewidth": 0.8,
                            "shrinkA": 2, "shrinkB": 5})


def hline(ax, y, text=None, x_text=None, va="bottom"):
    ax.axhline(y, color=REFERENCE, linewidth=1.2, linestyle=(0, (4, 3)))
    if text:
        ax.text(x_text, y, text, color=TEXT_SECONDARY, fontsize=10, va=va, ha="right")


def vline(ax, x, text=None, y_text=None):
    ax.axvline(x, color=REFERENCE, linewidth=1.2, linestyle=(0, (4, 3)))
    if text:
        ax.text(x, y_text, " " + text, color=TEXT_SECONDARY, fontsize=10, va="top", ha="left")


# ---------------------------------------------------------------- ①

def fig1(out):
    fig, ax = new_fig("① 작용 세기 c와 효과 E = c ÷ (1 + c)")
    c = np.linspace(0, 6, 400)
    ax.plot(c, c / (1 + c), color=BLUE, linewidth=2.2)
    ax.plot(c, c, color=REFERENCE, linewidth=1.8, linestyle="--")
    hline(ax, 1, "점근선 E = 1", 5.95)
    label(ax, 3.2, 0.62, "E = c ÷ (1 + c)", color=BLUE)
    label(ax, 1.45, 1.17, "비교: E = c")
    point(ax, 1, 0.5, "c = 1 → E = 0.5")
    ax.set_xlim(0, 6)
    ax.set_ylim(0, 1.3)
    return finish(fig, ax, out / "fig1_E_of_c.png", "작용 세기 c", "효과 E")


# ---------------------------------------------------------------- ②

def fig2(out):
    fig, ax = new_fig("② E = 1 − 1 ÷ (1 + c): y = −1/x를 평행이동한 곡선")
    ax.axvspan(0, 5, color=BLUE, alpha=0.06, linewidth=0)
    ax.text(2.6, -3.75, "실제 작용 세기 범위 c ≥ 0", color=TEXT_SECONDARY, fontsize=9)
    x = np.linspace(0.2, 5, 300)
    ax.plot(x, -1 / x, color=REFERENCE, linewidth=1.6, linestyle=":")
    label(ax, 3.3, -0.62, "원래 곡선 y = −1/x")
    c = np.linspace(-0.79, 5, 500)
    ax.plot(c, 1 - 1 / (1 + c), color=BLUE, linewidth=2.2)
    label(ax, 2.6, 0.45, "E = 1 − 1 ÷ (1 + c)", color=BLUE)
    hline(ax, 1, "점근선 E = 1", 4.95)
    vline(ax, -1, "점근선 c = −1", 1.5)
    ax.axhline(0, color=TEXT_SECONDARY, linewidth=0.8)
    ax.axvline(0, color=TEXT_SECONDARY, linewidth=0.8)
    ax.annotate("", xy=(0.6, -0.666 + 1), xytext=(1.6, -0.625),
                arrowprops={"arrowstyle": "->", "color": TEXT_SECONDARY, "linewidth": 1.2})
    ax.text(1.75, -1.25, "x축 −1, y축 +1\n평행이동", color=TEXT_SECONDARY, fontsize=9)
    point(ax, 0, 0, "(0, 0)", dx=-42, dy=6)
    ax.set_xlim(-1.5, 5)
    ax.set_ylim(-4, 1.6)
    return finish(fig, ax, out / "fig2_translation.png", "작용 세기 c", "효과 E")


# ---------------------------------------------------------------- ③

def fig3(out):
    fig, ax = new_fig("③ E = c ÷ (1 + c)와 역함수 c = e ÷ (1 − e)")
    x = np.linspace(0, 4, 400)
    ax.plot(x, x / (1 + x), color=BLUE, linewidth=2.2)
    e = np.linspace(0, 0.8, 400)
    ax.plot(e, e / (1 - e), color=ORANGE, linewidth=2.2, linestyle="--")
    ax.plot([0, 4], [0, 4], color=REFERENCE, linewidth=1.4, linestyle=":")
    label(ax, 2.6, 0.62, "E = c ÷ (1 + c)", color=BLUE)
    label(ax, 0.83, 3.1, "역함수\nc = e ÷ (1 − e)", color=ORANGE)
    label(ax, 3.35, 3.05, "y = x")
    ax.plot([1, 0.5], [0.5, 1], color=TEXT_SECONDARY, linewidth=1, linestyle=":")
    point(ax, 1, 0.5, "(1, 0.5)", dx=8, dy=-14)
    point(ax, 0.5, 1, "(0.5, 1)", dx=-52, dy=4)
    ax.set_xlim(0, 4)
    ax.set_ylim(0, 4)
    ax.set_aspect("equal")
    return finish(fig, ax, out / "fig3_inverse.png", "가로축 (c 또는 e)", "세로축 (E 또는 c)")


# ---------------------------------------------------------------- ④

def fig4(out):
    fig, ax = new_fig("④ 평균 농도 변화 r = 1 ÷ (1 − f·s)")
    s = np.linspace(0, 0.99, 500)
    for f, color in zip((0.4, 0.7, 1.0), ORDINAL_3):
        ax.plot(s, 1 / (1 - f * s), color=color, linewidth=2.2)
    label(ax, 0.9, 1.3, "f = 0.4", color=ORDINAL_3[0])
    label(ax, 0.86, 3.0, "f = 0.7", color=ORDINAL_3[1])
    label(ax, 0.55, 6.0, "f = 1.0\n(s = 0.99에서 r = 100)", color=ORDINAL_3[2])
    point(ax, 0.6, model.r_from_fractions([(0.7, 1 - 0.6)]), "f = 0.7, s = 0.6 → r = 1.724",
          dx=10, dy=-6)
    hline(ax, 1)
    ax.set_xlim(0, 1)
    ax.set_ylim(0.8, 8)
    return finish(fig, ax, out / "fig4_r_of_s.png", "억제 정도 s", "평균 농도 변화 r")


# ---------------------------------------------------------------- ⑤

def fig5(out):
    fig, ax = new_fig("⑤ 억제 정도 s = x ÷ (1 + x), x = 농도 ÷ Ki")
    x = np.linspace(0, 10, 400)
    ax.plot(x, x / (1 + x), color=BLUE, linewidth=2.2)
    hline(ax, 1, "점근선 s = 1", 9.95)
    point(ax, 1, 0.5, "농도 = Ki → s = 0.5")
    label(ax, 5.5, 0.75, "s = x ÷ (1 + x)", color=BLUE)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 1.15)
    return finish(fig, ax, out / "fig5_s_of_x.png", "x = 농도 ÷ Ki", "억제 정도 s")


# ---------------------------------------------------------------- ⑥

def fig6(out):
    fig, ax = new_fig("⑥ 차단제가 있을 때 작용제의 효과 E = c ÷ (1 + c + c_ant)")
    c = np.linspace(0, 15, 500)
    ys = []
    for c_ant, color in zip((0, 1, 3), ORDINAL_3):
        y = c / (1 + c + c_ant)
        ys.append(y)
        ax.plot(c, y, color=color, linewidth=2.2)
    for (c_ant, color, yy) in zip((0, 1, 3), ORDINAL_3, ys):
        ax.text(15.2, yy[-1], f"c_ant = {c_ant}", color=color, fontsize=10, va="center")
    hline(ax, 1, "점근선 E = 1", 14.9)
    point_arrow(ax, 1, model.target_effect([1], [1]), "c = 1, c_ant = 1 → 0.333", 5.0, 0.12)
    point_arrow(ax, 3, model.target_effect([3], [1]), "c = 3, c_ant = 1 → 0.6", 5.5, 0.3)
    ax.set_xlim(0, 17.5)
    ax.set_ylim(0, 1.1)
    return finish(fig, ax, out / "fig6_antagonist.png", "작용제의 작용 세기 c", "대상의 작용 E")


# ---------------------------------------------------------------- ⑦

def fig7(out):
    fig, ax = new_fig(r"⑦ 두 대상 $c_1 = c_2 = c$를 합친 효과와 k")
    c = np.linspace(0, 2, 400)
    e = c / (1 + c)
    ax.plot(c, 2 * e, color=REFERENCE, linewidth=1.8, linestyle="--")
    ax.text(1.35, 2 * (1.35 / 2.35) + 0.04, "효과 단순 합 2 × c ÷ (1 + c)", color=TEXT_SECONDARY,
            fontsize=10, ha="right")
    ends = []
    for k, color in zip((0, 1, 4, 8), ORDINAL_4):
        y = np.array([model.combine([ei, ei], k) for ei in e])
        ax.plot(c, y, color=color, linewidth=2.2)
        ends.append((k, color, y[-1]))
        at = model.combine([model.e_from_c(0.25)] * 2, k)
        ax.plot([0.25], [at], marker="o", markersize=6, color=color, markeredgecolor=SURFACE,
                markeredgewidth=1.2, zorder=5)
    y_prev = -1.0
    for k, color, y_end in sorted(ends, key=lambda x: x[2]):
        y_prev = max(y_end, y_prev + 0.06)
        ax.text(2.03, y_prev, f"k = {k}", color=color, fontsize=10, va="center")
    ax.axvline(0.25, color=REFERENCE, linewidth=1, linestyle=":")
    ax.text(0.27, 1.32, "c = 0.25: 0.333, 0.36, 0.429, 0.5", color=TEXT_SECONDARY, fontsize=9)
    hline(ax, 1, "E = 1", 0.45)
    ax.set_xlim(0, 2.25)
    ax.set_ylim(0, 1.4)
    return finish(fig, ax, out / "fig7_two_targets_k.png", "각 대상의 작용 세기 c", "합친 효과")


FIGURES = [fig1, fig2, fig3, fig4, fig5, fig6, fig7]


def main(argv=None):
    ap = argparse.ArgumentParser(description="보고서용 그래프")
    ap.add_argument("--out", default=str(OUT_DIR / "figures"))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not setup_font():
        print("한글 글꼴을 찾지 못해 글자가 깨질 수 있다(맑은 고딕, 애플고딕, 나눔고딕 중 하나를 설치).")
    paths = [f(out) for f in FIGURES]
    for p in paths:
        print(f"저장: {p}")
    print(DISCLAIMER)
    return paths


if __name__ == "__main__":
    main()
