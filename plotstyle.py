"""그래프 공통 스타일(색, 글꼴, 축)."""
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
REFERENCE = "#8a8984"        # 점근선·비교선 같은 기준선
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
ORDINAL_3 = ["#6da7ec", "#256abf", "#0d366b"]            # 순서가 있는 값 3개(밝음 → 어두움)
ORDINAL_4 = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]  # 순서가 있는 값 4개

KOREAN_FONTS = ["Malgun Gothic", "AppleGothic", "Apple SD Gothic Neo", "NanumGothic",
                "NanumBarunGothic", "Noto Sans CJK KR", "Noto Sans KR", "UnDotum"]


def setup_font():
    """한글 글꼴이 있으면 쓰고 True, 없으면 False."""
    from matplotlib import font_manager, rcParams
    have = {f.name for f in font_manager.fontManager.ttflist}
    for name in KOREAN_FONTS:
        if name in have:
            rcParams["font.family"] = [name, "DejaVu Sans"]   # 한글 글꼴에 없는 기호(−, ₁ 등)는 대체 글꼴로
            rcParams["axes.unicode_minus"] = True
            return True
    return False


def style_axes(ax, grid_axis="y"):
    ax.set_facecolor(SURFACE)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
