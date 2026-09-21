import numpy as np

from app.core.background import remove_background


def _canvas(h=20, w=20):
    rgba = np.zeros((h, w, 4), dtype=np.float32)
    rgba[..., :3] = 1.0
    rgba[..., 3] = 1.0
    rgba[5:15, 5:15, :3] = [1.0, 0.0, 0.0]
    return rgba


def test_flood_from_corner_clears_only_connected_background():
    out = remove_background(_canvas(), seed_xy=(0, 0), tolerance=0.05)
    assert out[0, 0, 3] == 0.0 and out[19, 19, 3] == 0.0
    assert out[10, 10, 3] == 1.0 and out[10, 10, 0] == 1.0


def test_enclosed_region_not_touched_by_outer_flood():
    rgba = _canvas()
    rgba[8:12, 8:12, :3] = 1.0
    out = remove_background(rgba, seed_xy=(0, 0), tolerance=0.05)
    assert out[10, 10, 3] == 1.0


def test_tolerance_controls_spread():
    rgba = _canvas()
    rgba[0:20, 0:3, :3] = [0.97, 0.97, 0.97]
    strict = remove_background(rgba, seed_xy=(19, 19), tolerance=0.01)
    loose = remove_background(rgba, seed_xy=(19, 19), tolerance=0.1)
    assert strict[10, 1, 3] == 1.0
    assert loose[10, 1, 3] == 0.0


def test_input_not_mutated():
    rgba = _canvas()
    before = rgba.copy()
    remove_background(rgba, seed_xy=(0, 0))
    assert np.array_equal(rgba, before)


# ---- 自动去掉纯色背景 ----------------------------------------------------------------
# 背景：示例草莓出图时，外面一大圈背景 H21 全填了豆——拼豆一般是拼一个"形状"，
# 不是一整块矩形。后端早有去背景功能但要手点一个背景像素，前端从没做入口。

from pathlib import Path  # noqa: E402

from app.core.background import BORDER_MIN_SHARE, remove_border_background  # noqa: E402


def _subject_on_white(h=60, w=60):
    rgba = np.ones((h, w, 4), dtype=np.float32)                   # 白底
    rgba[15:45, 15:45, :3] = [0.9, 0.2, 0.25]                     # 红色主体
    return rgba


def test_solid_background_is_removed_and_subject_kept():
    out, found = remove_border_background(_subject_on_white())
    assert found
    assert out[0, 0, 3] == 0 and out[59, 59, 3] == 0 and out[5, 30, 3] == 0
    assert out[30, 30, 3] == 1


def test_background_colored_holes_inside_the_subject_are_kept():
    """伞盖上的白点、眼睛高光和背景同色，但被主体包着——不能当背景删掉。"""
    rgba = _subject_on_white()
    rgba[28:32, 28:32, :3] = 1.0                                  # 主体中间一块白
    out, _ = remove_border_background(rgba)
    assert out[30, 30, 3] == 1


def test_background_split_by_the_subject_is_removed_on_both_sides():
    """主体碰到上下边缘、把背景隔成左右两块：两块都要去掉，不能只去一个角那块。"""
    rgba = np.ones((60, 60, 4), dtype=np.float32)
    rgba[:, 25:35, :3] = [0.9, 0.2, 0.25]                         # 竖条贯穿上下
    out, found = remove_border_background(rgba)
    assert found
    assert out[30, 5, 3] == 0 and out[30, 55, 3] == 0
    assert out[30, 30, 3] == 1


def test_photos_with_a_busy_border_are_left_alone():
    """照片边缘颜色不统一，不去背景——实测照片边缘同色占比最高 66.8%。"""
    rng = np.random.default_rng(0)
    rgba = np.ones((60, 60, 4), dtype=np.float32)
    rgba[..., :3] = rng.random((60, 60, 3))
    out, found = remove_border_background(rgba)
    assert not found
    assert (out[..., 3] == 1).all()


def test_mostly_uniform_border_below_the_threshold_is_left_alone():
    """上半边天空、下半边草地：边缘不是一个颜色，是风景的一部分，不该被当背景删。"""
    rgba = np.ones((60, 60, 4), dtype=np.float32)
    rgba[:30, :, :3] = [0.5, 0.7, 0.95]
    rgba[30:, :, :3] = [0.3, 0.6, 0.2]
    _, found = remove_border_background(rgba)
    assert not found
    assert BORDER_MIN_SHARE >= 0.9


def test_already_transparent_background_is_a_no_op():
    rgba = _subject_on_white()
    rgba[..., 3] = 0
    rgba[15:45, 15:45, 3] = 1
    out, found = remove_border_background(rgba)
    assert not found and np.array_equal(out, rgba)


def test_large_images_are_handled_at_full_size():
    """大图先缩小算掩码再放大回原尺寸：输出必须还是原尺寸。"""
    rgba = np.ones((2200, 1800, 4), dtype=np.float32)
    rgba[800:1400, 600:1200, :3] = [0.9, 0.2, 0.25]
    out, found = remove_border_background(rgba)
    assert found and out.shape == rgba.shape
    assert out[10, 10, 3] == 0 and out[1100, 900, 3] == 1


def test_pipeline_leaves_the_strawberry_background_empty():
    from app.core import pipeline
    from app.core.palette import Palette
    from app.core.types import EMPTY, Params
    pal = Palette.load("mard")
    png = (Path(__file__).resolve().parents[2] / "frontend" / "public" / "samples"
           / "strawberry.png").read_bytes()
    kept = pipeline.run(png, Params(grid_long_side=40), pal)
    cut = pipeline.run(png, Params(grid_long_side=40, remove_background=True), pal)
    assert (kept.grid != EMPTY).all()                             # 不开：整块矩形全填豆
    assert cut.grid[0, 0] == EMPTY and cut.grid[-1, -1] == EMPTY  # 开：背景不填豆
    assert (cut.grid != EMPTY).sum() < (kept.grid != EMPTY).sum() / 2
    assert cut.grid[20, 20] != EMPTY                              # 草莓本体还在


def test_non_bool_remove_background_is_rejected():
    import pytest

    from app.services.patterns import PatternError, params_from_dict
    with pytest.raises(PatternError):
        params_from_dict({"remove_background": "yes"})
