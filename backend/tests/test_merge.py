import numpy as np

from app.core.merge import color_counts, detect_outline_cells, merge_small_colors


def _lab():
    return np.array([[50, 0, 0], [52, 1, 0], [90, 0, 0], [10, 0, 0]], dtype=float)   # 0 与 1 很接近


def test_color_counts_ignores_empty():
    g = np.array([[0, 0, -1], [1, -1, 2]], dtype=np.int16)
    assert color_counts(g) == {0: 2, 1: 1, 2: 1}


def test_small_color_merges_into_nearest_present_color():
    g = np.full((5, 5), 2, dtype=np.int16)
    g[0, 0] = 1                       # 只有 1 颗
    g[1:3, 1:3] = 0                   # 4 颗
    out, log = merge_small_colors(g, _lab(), threshold=3)
    assert out[0, 0] == 0             # 1 → 0（最近，且 0 在图中）
    assert log[0][0] == 1 and log[0][1] == 0 and log[0][2] < 3
    assert (out == 1).sum() == 0


def test_merge_processes_smallest_first_and_cascades():
    g = np.full((6, 6), 2, dtype=np.int16)
    g[0, 0] = 1
    g[0, 1] = 0
    out, log = merge_small_colors(g, _lab(), threshold=3)
    assert set(np.unique(out).tolist()) == {2}
    assert len(log) == 2


def test_protected_color_not_merged():
    g = np.full((5, 5), 2, dtype=np.int16)
    g[0, 0] = 3
    out, log = merge_small_colors(g, _lab(), threshold=3, protected={3})
    assert out[0, 0] == 3 and log == []


def test_outline_detection_finds_thin_dark_lines_only():
    rgb = np.ones((10, 10, 3), dtype=np.float32)
    rgb[5, :, :] = 0.05                 # 一条 1 格宽黑线
    rgb[0:3, 0:3, :] = 0.05             # 一块 3×3 黑块（不是描边）
    mask = np.ones((10, 10), bool)
    out = detect_outline_cells(rgb, mask)
    assert out[5, 5] and not out[1, 1]
    assert not out[7, 7]
