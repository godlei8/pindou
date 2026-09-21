"""平涂插画：每格取原图自己的一种颜色，不出抗锯齿过渡色。

背景：草莓样图描边 7px、每格 8.3px，描边盖不满任何一格。面积平均后描边变成
F6/R22/R13 三种深红交替，每颗籽由四种颜色拼成，可拼性 74.8。
"""
import io

import numpy as np
import pytest
from PIL import Image, ImageDraw
from scipy import ndimage

from app.core import flat, pipeline
from app.core.color import pairwise_delta_e, srgb_to_lab
from app.core.downsample import downsample_area
from app.core.palette import Palette
from app.core.types import EMPTY, Params

CREAM, RED, INK, YELLOW = (252, 246, 230), (232, 58, 66), (59, 47, 35), (255, 219, 77)


def _illustration(size=480, stroke=7) -> bytes:
    """像草莓样图：奶油底 + 红色椭圆 + 深色细描边 + 几颗黄色小籽，带抗锯齿（4 倍画再缩小）。"""
    s = 4
    im = Image.new("RGB", (size * s, size * s), CREAM)
    d = ImageDraw.Draw(im)
    box = [60 * s, 90 * s, 420 * s, 420 * s]
    d.ellipse(box, fill=RED, outline=INK, width=stroke * s)
    for cx, cy in ((170, 200), (300, 210), (240, 300), (180, 350), (310, 340)):
        d.ellipse([(cx - 6) * s, (cy - 8) * s, (cx + 6) * s, (cy + 8) * s], fill=YELLOW)
    im = im.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def pal():
    return Palette.load("mard")


def _rgba(png: bytes) -> np.ndarray:
    from app.core.image_io import load_rgba
    return load_rgba(png)


# ---- 认墨 ------------------------------------------------------------------------

def test_detects_the_few_inks_of_a_flat_illustration():
    inks = flat.detect_inks(_rgba(_illustration()))
    assert inks is not None
    got = {tuple(int(round(v)) for v in c * 255) for c in inks}
    for want in (CREAM, RED, INK, YELLOW):
        assert min(sum(abs(a - b) for a, b in zip(want, g)) for g in got) <= 6, want


def test_a_photo_has_no_inks(rng):
    """颜色连续变化的图（照片）认不出几种墨，走原来的面积平均。"""
    y, x = np.mgrid[0:200, 0:200] / 200.0
    img = np.stack([x, y, 0.5 + 0.3 * np.sin(6 * x)], -1) + rng.normal(0, 0.03, (200, 200, 3))
    rgba = np.concatenate([np.clip(img, 0, 1), np.ones((200, 200, 1))], -1).astype(np.float32)
    assert flat.detect_inks(rgba) is None


def test_transparent_background_is_ignored():
    rgba = np.zeros((100, 100, 4), np.float32)
    rgba[20:80, 20:80] = [1, 0, 0, 1]
    rgba[20:80, 45:55] = [0, 0, 1, 1]
    inks = flat.detect_inks(rgba)
    assert inks is not None and len(inks) == 2          # 透明区的黑色不算一种墨


# ---- 取色 ------------------------------------------------------------------------

def test_cells_only_take_source_inks_not_mixtures():
    rgba = _rgba(_illustration())
    inks = flat.detect_inks(rgba)
    area = downsample_area(rgba, 58, 58)
    cells = flat.downsample_inks(rgba, 58, 58, inks, area.coverage)
    used = np.unique(cells.rgb.reshape(-1, 3), axis=0)
    assert len(used) <= len(inks)
    assert all(np.isclose(inks, u, atol=1e-6).all(1).any() for u in used)
    # 对照：面积平均会混出一大堆过渡色
    assert len(np.unique(np.round(area.rgb.reshape(-1, 3), 2), axis=0)) > 3 * len(inks)


def _cells(paint, base, inks, size=80, grid=10):
    rgba = np.ones((size, size, 4), np.float32)
    rgba[..., :3] = np.array(base) / 255
    paint(rgba)
    arr = np.array(inks, np.float32) / 255
    return flat.downsample_inks(rgba, grid, grid, arr, np.ones((grid, grid), np.float32)), arr


def test_a_thin_dark_line_is_kept_and_continuous():
    """线比格子窄得多（每格只占三成）：按"谁多用谁"一格都拿不到，整条线会消失。"""
    def paint(rgba):
        rgba[:, 34:37, :3] = np.array(INK) / 255             # 3px 的竖线，一格 8px
    cells, inks = _cells(paint, RED, [RED, INK])
    dark = np.isclose(cells.rgb, inks[1]).all(-1)
    assert dark[:, 4].all() and dark.sum() == 10


def test_a_thin_light_line_is_kept_too():
    """不只是深色线：深底上的浅色细线一样要留住（没有"最深的颜色才是描边"这种特例）。"""
    def paint(rgba):
        rgba[:, 34:37, :3] = np.array(CREAM) / 255
    cells, inks = _cells(paint, INK, [INK, CREAM])
    light = np.isclose(cells.rgb, inks[1]).all(-1)
    assert light[:, 4].all() and light.sum() == 10


def test_a_small_feature_straddling_cells_keeps_a_cell():
    """一块半格多的黄色跨在四格交界上，每格都只有一成多——按"谁多用谁"会整块消失。"""
    def paint(rgba):
        rgba[37:43, 37:43, :3] = np.array(YELLOW) / 255      # 36 px，每格只分到 9 px
    cells, inks = _cells(paint, RED, [RED, YELLOW])
    assert np.isclose(cells.rgb, inks[1]).all(-1).sum() == 1


# ---- 整条流水线 --------------------------------------------------------------------

def _run(pal, n=58, **kw):
    return pipeline.run(_illustration(), Params(grid_long_side=n, remove_background=True, **kw), pal)


def test_outline_is_one_color_and_it_is_the_real_ink(pal):
    res = _run(pal)
    g = res.grid
    mask = g != EMPTY
    edge = mask & ~ndimage.binary_erosion(mask, border_value=0)
    codes, counts = np.unique(g[edge], return_counts=True)
    main = codes[counts.argmax()]
    ink_de = pairwise_delta_e(srgb_to_lab(np.array([INK]) / 255.0), pal.lab[[main]]).item()
    assert ink_de < 5, "描边应该配到原图的墨色（H16），不是现有颜色里最深的某个灰"
    assert counts.max() / counts.sum() > 0.95, f"描边混了多种颜色：{dict(zip(codes, counts))}"


def test_no_transition_colors_eat_palette_slots(pal):
    # 关掉小色号合并：58 格下五颗籽一共 5 颗豆，会按设置并掉——那是另一个功能，这里只看取色
    res = _run(pal, small_color_threshold=0)
    assert len(res.color_stats) == 3                     # 红、墨、黄（奶油底已去掉）
    assert res.report.confetti_pct < 5


def test_seeds_are_a_single_color(pal):
    res = _run(pal, n=80)
    yellow = pairwise_delta_e(srgb_to_lab(np.array([YELLOW]) / 255.0), pal.lab).argmin()
    seeds, n = ndimage.label(res.grid == yellow)
    assert n == 5, "五颗籽，每颗一块黄色"
