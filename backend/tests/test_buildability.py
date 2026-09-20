import numpy as np

from app.core.buildability import analyze

LAB = np.array([[50, 0, 0], [80, 0, 0], [20, 0, 0], [92, 0, 2]], dtype=float)  # 索引 3 = 透明豆


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


# ---------- 评分必须能反映改善（浏览器验收发现的缺陷） ----------

CLEAR = 3          # LAB 里索引 3 当作透明豆


def test_clear_bridge_is_not_penalized_as_thin_line():
    """透明豆桥天生 1 格宽，但它是结构支撑不是脆弱悬臂，不该当细线扣分。

    两块必须够厚（3×3），否则它们自己就是细线，测不出桥的豁免。
    """
    g = np.full((7, 11), -1, dtype=np.int16)
    g[2:5, 0:3] = 0               # 左块 3×3
    g[2:5, 8:11] = 1              # 右块 3×3
    without = analyze(g.copy(), LAB, clear_index=CLEAR)
    g[3, 3:8] = CLEAR             # 中间一行透明豆搭桥
    with_bridge = analyze(g, LAB, clear_index=CLEAR)

    assert without.n_components == 2
    assert with_bridge.n_components == 1
    assert without.metrics["thin_ratio"] == 0.0       # 两个厚块，本来就没细线
    assert with_bridge.metrics["thin_ratio"] == 0.0   # 加了桥之后仍然没有
    assert with_bridge.score > without.score          # 连上了，分数该涨


def test_clear_bridge_without_exemption_would_count_as_thin():
    """对照组：不告诉 analyze 哪个是透明豆，同一座桥就会被当细线扣分。"""
    g = np.full((7, 11), -1, dtype=np.int16)
    g[2:5, 0:3] = 0
    g[2:5, 8:11] = 1
    g[3, 3:8] = CLEAR
    assert analyze(g, LAB).metrics["thin_ratio"] > 0.0


def test_thin_line_of_normal_colors_still_penalized():
    """只豁免透明豆，普通颜色的细线照扣。"""
    g = np.full((7, 7), -1, dtype=np.int16)
    g[3, :] = 0
    r = analyze(g, LAB, clear_index=CLEAR)
    assert r.metrics["thin_ratio"] > 0.9


def test_score_improves_when_metrics_improve_even_on_bad_patterns():
    """核心回归：很糟的图上做出真实改善，分数必须上升。

    旧公式各项扣分封顶，在这种图上全部触顶，改善一分都反映不出来，
    反而因为新增的细线项倒扣，出现"接受建议后分数下降"。
    """
    bad = np.full((12, 12), -1, dtype=np.int16)
    for i in range(12):
        bad[i, i] = 0                      # 纯对角线：全是孤立豆 + 对角虚连 + 不连通
    worse = analyze(bad, LAB, clear_index=CLEAR)

    better = bad.copy()
    for i in range(11):
        better[i + 1, i] = CLEAR           # 补透明豆，连成一片
    improved = analyze(better, LAB, clear_index=CLEAR)

    assert improved.n_components < worse.n_components
    assert improved.metrics["n_isolated"] < worse.metrics["n_isolated"]
    assert improved.metrics["n_diagonal"] < worse.metrics["n_diagonal"]
    assert improved.score > worse.score, (
        f"改善了却掉分：{worse.score} -> {improved.score}")


def test_score_is_monotonic_across_a_repair_sequence():
    """连续修复：每一步都不该让分数倒退。"""
    g = np.full((10, 10), -1, dtype=np.int16)
    for i in range(10):
        g[i, i] = 0
    scores = [analyze(g, LAB, clear_index=CLEAR).score]
    for i in range(9):
        g[i + 1, i] = CLEAR
        scores.append(analyze(g, LAB, clear_index=CLEAR).score)
    assert scores == sorted(scores), f"分数出现倒退：{scores}"


def test_perfect_pattern_still_scores_100():
    assert analyze(np.zeros((8, 8), dtype=np.int16), LAB, clear_index=CLEAR).score == 100.0
