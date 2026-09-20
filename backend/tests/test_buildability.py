import numpy as np

from app.core.buildability import analyze

LAB = np.array([[50, 0, 0], [80, 0, 0], [20, 0, 0]], dtype=float)


def _issues(report, t):
    return [i for i in report.issues if i.type == t]


def test_solid_block_is_perfect():
    g = np.zeros((6, 6), dtype=np.int16)
    r = analyze(g, LAB)
    assert r.n_components == 1 and r.issues == [] and r.score == 100.0 and r.confetti_pct == 0.0


def test_disconnected_components_reported():
    g = np.full((6, 6), -1, dtype=np.int16)
    g[0:2, 0:2] = 0
    g[4:6, 4:6] = 1
    r = analyze(g, LAB)
    assert r.n_components == 2
    assert len(_issues(r, "disconnected")) == 1
    assert len(_issues(r, "disconnected")[0].cells) == 4


def test_isolated_bead_and_diagonal_link():
    # (3,3) 与 (0,0)/(1,1) 都不相邻，确保两种现象互不重叠
    g = np.full((5, 5), -1, dtype=np.int16)
    g[3, 3] = 0                    # 孤立：4-邻域与对角邻域全空
    g[0, 0] = 1; g[1, 1] = 1       # 对角虚连
    r = analyze(g, LAB)
    iso = _issues(r, "isolated_bead")
    assert (3, 3) in [c for i in iso for c in i.cells]
    diag = _issues(r, "diagonal_link")
    assert len(diag) == 1 and sorted(diag[0].cells) == [(0, 0), (1, 1)]


def test_isolated_bead_can_also_be_a_diagonal_link():
    """对角相连的两格：每格 4-邻域都空，所以既是孤立豆又是对角虚连——两条都该报。"""
    g = np.full((4, 4), -1, dtype=np.int16)
    g[0, 0] = 0; g[1, 1] = 0
    r = analyze(g, LAB)
    assert len(_issues(r, "isolated_bead")) == 2
    assert len(_issues(r, "diagonal_link")) == 1


def test_thin_line_detected():
    g = np.full((7, 7), -1, dtype=np.int16)
    g[3, :] = 0                    # 1 格宽横线
    r = analyze(g, LAB)
    assert len(_issues(r, "thin_line")) == 1
    assert r.metrics["thin_ratio"] > 0.9


def test_hole_detected_but_border_gap_is_not():
    g = np.zeros((7, 7), dtype=np.int16)
    g[3, 3] = -1                   # 内部空洞
    g[0, 0] = -1                   # 边角缺口，不是洞
    r = analyze(g, LAB)
    holes = _issues(r, "hole")
    assert len(holes) == 1 and holes[0].cells == [(3, 3)]


def test_small_color_has_target_and_delta_e():
    g = np.zeros((6, 6), dtype=np.int16)
    g[0, 0] = 2
    r = analyze(g, LAB, small_color_threshold=3)
    sc = _issues(r, "small_color")
    assert len(sc) == 1 and sc[0].target_color == 0 and sc[0].delta_e is not None


def test_confetti_pct_and_protection():
    g = np.zeros((10, 10), dtype=np.int16)
    g[4, 4] = 1                    # 1 颗异色，四周都是 0
    r = analyze(g, LAB)
    assert abs(r.confetti_pct - 1.0) < 1e-6
    r2 = analyze(g, LAB, protected_cells={(4, 4)})
    assert r2.confetti_pct == 0.0


def test_score_decreases_with_problems():
    good = analyze(np.zeros((8, 8), dtype=np.int16), LAB).score
    bad = np.full((8, 8), -1, dtype=np.int16)
    bad[0, 0] = 0; bad[7, 7] = 1; bad[3, :] = 2
    assert analyze(bad, LAB).score < good - 30
