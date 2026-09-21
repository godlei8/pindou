"""描边闭合、眼睛高光（猫样图，2026-09-21）。

去掉背景后：轮廓断了 7 处（橙色直接挨着空白）、头顶弧线断开、眼睛高光丢了、眼睛胖了一圈。
"""
import io

import numpy as np
import pytest
from PIL import Image, ImageDraw
from scipy import ndimage

from app.core import flat, pipeline
from app.core.color import pairwise_delta_e, srgb_to_lab
from app.core.palette import Palette
from app.core.types import EMPTY, Params

INK, ORANGE, WHITE = (59, 47, 35), (245, 170, 80), (255, 255, 255)
PINK, ROSE = (250, 140, 150), (230, 90, 110)


def cat_png(size=480) -> bytes:
    """像猫样图：浅蓝底、橙色圆脸 + 7px 深色描边、两只深色眼睛各带一个白色高光、粉鼻子、粉腮红。"""
    s = 4
    im = Image.new("RGB", (size * s, size * s), (222, 238, 250))
    d = ImageDraw.Draw(im)
    d.ellipse([83 * s, 101 * s, 397 * s, 415 * s], fill=ORANGE, outline=INK, width=7 * s)
    for cx in (185, 295):
        d.ellipse([(cx - 18) * s, 215 * s, (cx + 18) * s, 265 * s], fill=INK)
        d.ellipse([(cx - 12) * s, 222 * s, (cx - 3) * s, 231 * s], fill=WHITE)
        x0 = cx - 75 if cx < 240 else cx + 45
        d.ellipse([x0 * s, 285 * s, (x0 + 30) * s, 305 * s], fill=PINK)
    d.polygon([(230 * s, 278 * s), (250 * s, 278 * s), (240 * s, 294 * s)], fill=ROSE)
    im = im.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def code_of(pal, rgb) -> int:
    return int(pairwise_delta_e(srgb_to_lab(np.array([rgb]) / 255.0), pal.lab).argmin())


def exposed(grid, line_color) -> int:
    """填充色上下左右直接挨着空白的格数——轮廓闭合的话应该是 0。"""
    mask = grid != EMPTY
    fill = mask & (grid != line_color)
    near_empty = ndimage.binary_dilation(~mask, structure=ndimage.generate_binary_structure(2, 1))
    return int((fill & near_empty).sum())


@pytest.fixture(scope="module")
def pal():
    return Palette.load("mard")


@pytest.fixture(scope="module")
def cat(pal):
    return pipeline.run(cat_png(), Params(remove_background=True), pal)


@pytest.mark.parametrize("n", [40, 58, 80])
def test_outline_encloses_the_shape_after_background_removal(pal, n):
    res = pipeline.run(cat_png(), Params(grid_long_side=n, remove_background=True), pal)
    assert exposed(res.grid, code_of(pal, INK)) == 0


def test_outline_is_one_bead_wide(cat, pal):
    """线骑在两格中间时只留一边，不出两颗宽的描边。"""
    line = cat.grid == code_of(pal, INK)
    eyes = ndimage.binary_opening(line, structure=np.ones((3, 3)))       # 实心块不算描边
    line &= ~ndimage.binary_dilation(eyes, iterations=2)
    thick = ndimage.binary_erosion(line, structure=np.ones((2, 2)))
    assert thick.sum() <= 2


def test_eye_highlights_survive(cat, pal):
    white, n = ndimage.label(cat.grid == code_of(pal, WHITE))
    assert n == 2, "两只眼睛各一个高光"
    ink = code_of(pal, INK)
    for sl in ndimage.find_objects(white):               # 高光在眼睛里面：周围多数是深色
        r, c = sl[0].start, sl[1].start
        assert (cat.grid[r - 1:r + 2, c - 1:c + 2] == ink).sum() >= 4


def test_eyes_are_not_fattened(cat, pal):
    """实心深色块按"过半才算"，不因为照顾描边被撑胖一圈。原图每只眼 36×50px ≈ 4.3×6 格。"""
    ink = cat.grid == code_of(pal, INK)
    blobs, n = ndimage.label(ndimage.binary_opening(ink, structure=np.ones((3, 3))))
    assert n == 2
    for sl in ndimage.find_objects(blobs):
        assert sl[0].stop - sl[0].start <= 7 and sl[1].stop - sl[1].start <= 5


def test_each_source_color_gets_its_closest_bead(cat, pal):
    """腮红和鼻子两种粉色各配各的，不被选色并成一种。"""
    assert code_of(pal, PINK) != code_of(pal, ROSE)
    assert {code_of(pal, PINK), code_of(pal, ROSE)} <= set(cat.color_stats)


def test_small_details_are_not_merged_away(cat, pal):
    """平涂图里每种颜色都是原图真有的：高光只有几颗豆也不并掉（默认阈值是 10 颗）。"""
    assert cat.params.small_color_threshold == 10
    assert 0 < cat.color_stats[code_of(pal, WHITE)] < 10


def _two_ink_cells(paint):
    rgba = np.ones((80, 80, 4), np.float32)
    rgba[..., :3] = np.array(ORANGE) / 255
    paint(rgba)
    inks = np.array([ORANGE, INK], np.float32) / 255
    cells = flat.downsample_inks(rgba, 10, 10, inks, np.ones((10, 10), np.float32))
    return np.isclose(cells.rgb, inks[1]).all(-1)


def test_thin_open_line_is_not_eaten_from_its_ends():
    """一条 3px 的细线（每格只占三成多）：削薄时不能从线头一格一格吃光。"""
    def paint(rgba):
        rgba[34:37, 8:72, :3] = np.array(INK) / 255
    dark = _two_ink_cells(paint)
    assert dark.sum() == 8 and dark[4, 1:9].all()


def test_scattered_dark_specks_do_not_become_beads():
    """零星一点深色（占一格不到两成、周围没有更深的）不算描边。"""
    def paint(rgba):
        rgba[17:20, 17:21, :3] = np.array(INK) / 255     # 12px，一格 64px
    assert not _two_ink_cells(paint).any()


def test_a_line_straddling_two_rows_stays_connected():
    """线正好骑在两行格子中间、两边各占四成：只留一行，而且是连续的。"""
    def paint(rgba):
        rgba[29:35, :, :3] = np.array(INK) / 255          # 6px：上一行 3px、下一行 3px
    dark = _two_ink_cells(paint)
    assert dark.sum() == 10
    assert dark[3].all() or dark[4].all()


SAMPLES = __import__("pathlib").Path(__file__).resolve().parents[2] / "frontend" / "public" / "samples"


@pytest.mark.parametrize("name", ["cat", "strawberry", "mushroom"])
@pytest.mark.parametrize("n", [40, 58, 80])
def test_home_page_samples_have_closed_outlines(pal, name, n):
    """首页的三张样图就是用户第一眼看到的效果（猫样图 58 格原来断 7 处）。"""
    path = SAMPLES / f"{name}.png"
    if not path.exists():
        pytest.skip("前端样图不在")
    res = pipeline.run(path.read_bytes(), Params(grid_long_side=n, remove_background=True), pal)
    assert exposed(res.grid, code_of(pal, INK)) == 0
