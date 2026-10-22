import matplotlib.image as mpimg

import figures


def test_seven_figures_at_200dpi(tmp_path):
    paths = figures.main(["--out", str(tmp_path)])
    assert len(paths) == 7
    for p in paths:
        img = mpimg.imread(p)
        assert img.shape[1] == round(7.5 * figures.DPI)   # 가로 7.5인치 × 200dpi
