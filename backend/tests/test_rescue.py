"""小而显眼的颜色（嘴唇这类）要能拿到名额。

背景：人像实拍出图时嘴唇消失。逐步诊断发现唇红在「选色」一步就没了——
k-medoids 最小化全图总误差，嘴唇只占十几格，对总误差贡献很小，
选出的 23 色里没有一个红色（嘴唇离最近可用色 OKLab 0.068，高于全图 99% 的格子）。
这和格数无关：87 格下照样消失。
"""
import numpy as np

from app.core.select import rescue_salient_colors

# 手搓一个小色卡（OKLab）：几种"大面积"色 + 一个红 + 一对几乎重复的色
PAL = np.array([
    [0.80, 0.02, 0.03],    # 0 肤色
    [0.30, 0.01, 0.01],    # 1 深发色
    [0.60, -0.02, -0.05],  # 2 灰蓝
    [0.62, 0.18, 0.08],    # 3 唇红
    [0.81, 0.02, 0.035],   # 4 与肤色几乎一样（差 0.011）
    [0.50, -0.20, 0.10],   # 5 一个谁都不像的绿
])


def _canvas(h=20, w=20, fill=0):
    ok = np.tile(PAL[fill], (h, w, 1)).astype(np.float64)
    return ok, np.ones((h, w), dtype=bool)


def test_a_coherent_far_patch_gets_a_color():
    ok, mask = _canvas()
    ok[10:12, 8:12] = PAL[3]                       # 2×4 的嘴唇
    working, rescued = rescue_salient_colors(ok, mask, PAL, np.array([0, 1, 2]), max_colors=24)
    assert rescued == [3]
    assert 3 in working


def test_a_single_far_cell_is_noise_not_a_feature():
    ok, mask = _canvas()
    ok[5, 5] = PAL[3]                              # 孤零零一格
    _, rescued = rescue_salient_colors(ok, mask, PAL, np.array([0, 1, 2]), max_colors=24)
    assert rescued == []


def test_at_the_cap_it_frees_a_near_duplicate_slot():
    """色数到上限时，从一对几乎一样的色里腾出名额，不突破用户设的上限。"""
    ok, mask = _canvas()
    ok[:, 10:] = PAL[4]                            # 右半边用那个"几乎肤色"——两色都有人用
    ok[2:4, 2:6] = PAL[3]
    working, rescued = rescue_salient_colors(ok, mask, PAL, np.array([0, 4, 1]), max_colors=3)
    assert rescued == [3]
    assert len(working) == 3
    assert 3 in working and 1 in working
    assert (0 in working) != (4 in working)        # 那对重复色里只留一个


def test_at_the_cap_without_duplicates_it_respects_the_cap():
    ok, mask = _canvas()
    ok[2:4, 2:6] = PAL[3]
    working, rescued = rescue_salient_colors(ok, mask, PAL, np.array([0, 1, 2]), max_colors=3)
    assert rescued == []
    assert sorted(working.tolist()) == [0, 1, 2]


def test_nothing_is_added_when_no_palette_color_is_close_either():
    """色卡里根本没有接近的颜色时，加了也白加。"""
    ok, mask = _canvas()
    ok[2:5, 2:6] = [0.4, 0.3, -0.3]                # 离色卡里所有颜色都远
    _, rescued = rescue_salient_colors(ok, mask, PAL, np.array([0, 1, 2]), max_colors=24)
    assert rescued == []


def test_masked_out_cells_never_count():
    ok, mask = _canvas()
    ok[10:12, 8:12] = PAL[3]
    mask[10:12, 8:12] = False                      # 那块是透明背景
    _, rescued = rescue_salient_colors(ok, mask, PAL, np.array([0, 1, 2]), max_colors=24)
    assert rescued == []


def _lip_scene(lip_rows=(20, 23), lip_cols=(18, 30)):
    """48×48 格的简单人脸：肤色 + 深发 + 一小块红嘴唇。直接按格子画，免得下采样再搅进来。"""
    import io

    from PIL import Image
    h = w = 48
    img = np.zeros((h, w, 3))
    img[:] = [0.88, 0.70, 0.62]                     # 肤色
    img[:, :8] = [0.20, 0.14, 0.11]                 # 头发
    img[lip_rows[0]:lip_rows[1], lip_cols[0]:lip_cols[1]] = [0.78, 0.22, 0.28]
    buf = io.BytesIO()
    Image.fromarray((img * 255).astype(np.uint8)).save(buf, format="PNG")
    return buf.getvalue(), lip_rows, lip_cols


def _no_red_selection(monkeypatch, pal):
    """模拟真实人像上 k-medoids 的结果：选出的色里没有红色。

    为什么要模拟：合成图太"干净"（24 个名额只用上 5–8 个），k-medoids 总能给嘴唇分到色，
    复现不了真照片里"名额被成千上万种细微色吃满、嘴唇在每个簇里都是少数"的情况
    （实测真实人像：嘴唇 17 格被拆进 G14/G13/M8 三个簇，占比 4.9%/9.7%/1.4%）。"""
    from app.core import pipeline
    real = pipeline.select_palette

    def fake(cell_ok, palette_ok, k, **kw):
        chosen = real(cell_ok, palette_ok, k, **kw)
        # 去掉所有偏红的色（OKLab a > 0.08）
        return np.array([c for c in chosen if palette_ok[c, 1] <= 0.08], dtype=np.int64)
    monkeypatch.setattr(pipeline, "select_palette", fake)


def _lip_de(res, pal, lip_rows, lip_cols):
    from app.core.color import pairwise_delta_e, srgb_to_lab
    got = pal.lab[res.grid[lip_rows[0]:lip_rows[1], lip_cols[0]:lip_cols[1]].ravel()]
    return float(np.median(pairwise_delta_e(got, srgb_to_lab(np.array([[0.78, 0.22, 0.28]]))).ravel()))


def test_pipeline_recovers_lips_that_the_selection_missed(monkeypatch):
    from app.core import pipeline
    from app.core.palette import Palette
    from app.core.types import Params
    pal = Palette.load("mard")
    _no_red_selection(monkeypatch, pal)
    png, lr, lc = _lip_scene()
    res = pipeline.run(png, Params(grid_long_side=48, max_colors=12), pal)
    assert _lip_de(res, pal, lr, lc) < 8, "嘴唇应该被补上一个红色，而不是配成最近的肤色"


def test_rescued_color_survives_small_color_merging(monkeypatch):
    """补回来的色往往只有几颗豆——低于「小色号合并」的阈值也不能被合并掉：
    为几颗豆多买一包是值得的，这正是人眼最先看的地方。"""
    from app.core import pipeline
    from app.core.palette import Palette
    from app.core.types import Params
    pal = Palette.load("mard")
    _no_red_selection(monkeypatch, pal)
    png, lr, lc = _lip_scene(lip_rows=(20, 22), lip_cols=(20, 24))      # 只有 8 格
    res = pipeline.run(png, Params(grid_long_side=48, max_colors=12, small_color_threshold=10), pal)
    assert _lip_de(res, pal, lr, lc) < 8
