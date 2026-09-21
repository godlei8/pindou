import numpy as np
from PIL import Image

from app.core.palette import Palette
from app.core.render import (RenderOptions, _code_key, cjk_font, materials, render_grid,
                             render_legend, render_sheet, text_color_for)
from app.core.split import Board


def _palette():
    return Palette.load("mard")


def test_canvas_size_is_integer_grid():
    g = np.zeros((10, 20), dtype=np.int16)
    img = render_grid(g, _palette(), RenderOptions(cell_px=20, axis=False))
    assert img.size == (20 * 20 + 1, 10 * 20 + 1)


def test_grid_lines_are_crisp_single_pixel():
    g = np.zeros((4, 4), dtype=np.int16)
    p = _palette()
    img = render_grid(g, p, RenderOptions(cell_px=20, axis=False, show_codes=False))
    arr = np.asarray(img)
    fill = tuple(p.rgb[0])
    line_col = arr[:, 20, :]            # 第二条竖线
    assert not np.all(line_col == fill, axis=1).any()      # 整列都不是填充色
    assert np.all(arr[10, 15] == fill)                     # 格子内部是填充色


def test_cell_filled_with_palette_color_and_highlight_drawn():
    g = np.zeros((3, 3), dtype=np.int16)
    p = _palette()
    img = render_grid(g, p, RenderOptions(cell_px=20, axis=False, show_codes=False, highlight=[(1, 1)]))
    arr = np.asarray(img)
    assert tuple(arr[5, 5]) == tuple(p.rgb[0])
    assert tuple(arr[21, 30]) == (255, 0, 0)               # 高亮框上边


def test_empty_cells_are_not_palette_colored():
    g = np.full((2, 2), -1, dtype=np.int16)
    img = render_grid(g, _palette(), RenderOptions(cell_px=20, axis=False))
    arr = np.asarray(img)
    assert arr.mean() > 200


def test_board_option_renders_only_that_board():
    g = np.zeros((10, 10), dtype=np.int16)
    img = render_grid(g, _palette(), RenderOptions(cell_px=10, axis=False, board=Board(0, 0, 4, 6, "A1")))
    assert img.size == (61, 41)


def test_text_color_contrast():
    assert text_color_for((250, 250, 250)) == (0, 0, 0)
    assert text_color_for((10, 10, 10)) == (255, 255, 255)


def test_materials_sorted_and_packed():
    g = np.zeros((10, 10), dtype=np.int16)
    g[0, :3] = 5
    rows = materials(g, _palette(), pack_size=50)
    assert rows[0]["index"] == 0 and rows[0]["count"] == 97 and rows[0]["packs"] == 2
    assert rows[1]["index"] == 5 and rows[1]["count"] == 3 and rows[1]["packs"] == 1
    assert rows[0]["code"] == _palette().codes[0]


def test_legend_renders():
    g = np.zeros((3, 3), dtype=np.int16)
    img = render_legend(materials(g, _palette()), _palette())
    assert isinstance(img, Image.Image) and img.size[1] >= 28



# ---- 材料清单 / 中文字体 ----------------------------------------------------

def _glyph(font, ch):
    im = Image.new("L", (80, 80), 0)
    from PIL import ImageDraw
    ImageDraw.Draw(im).text((10, 10), ch, fill=255, font=font)
    return np.asarray(im)


def test_cjk_font_really_has_chinese_glyphs():
    """回归：Pillow 默认字体没有中文，PDF 清单的「颗」「包」和页脚一直是方块。
    两个不同的字如果都画成同一个方块，位图就完全一样——真有字形才会不同。"""
    f = cjk_font(24)
    a, b = _glyph(f, "颗"), _glyph(f, "包")
    assert a.any() and b.any(), "什么都没画出来"
    assert not np.array_equal(a, b), "「颗」和「包」画得一模一样——多半是缺字方块"


def test_cjk_font_loads_the_bundled_truetype_not_the_fallback():
    from PIL import ImageFont
    assert isinstance(cjk_font(24), ImageFont.FreeTypeFont)
    assert "Fusion" in " ".join(cjk_font(24).getname())


def test_cjk_font_snaps_to_multiples_of_12():
    # 像素字体只在 12 的整数倍上清楚
    assert cjk_font(20).size == 24 and cjk_font(35).size == 36 and cjk_font(5).size == 12


def test_codes_sort_naturally():
    """拿豆子是按色号顺序翻豆盒：H3 要在 H11 前面，不能按字符串排。"""
    codes = ["H11", "ZG5", "H3", "A10", "A2", "H23"]
    assert sorted(codes, key=_code_key) == ["A2", "A10", "H3", "H11", "H23", "ZG5"]


def _many_colors():
    # 12 种颜色、用量各不相同
    g = np.repeat(np.arange(12, dtype=np.int16), np.arange(1, 13))
    return g.reshape(1, -1)


def test_legend_with_width_fills_multiple_columns():
    pal = _palette()
    rows = materials(_many_colors(), pal)
    single = render_legend(rows, pal)
    wide = render_legend(rows, pal, width=1600)
    assert wide.width == 1600
    assert wide.height < single.height / 2          # 铺开之后矮得多


def test_legend_reorders_internally_without_touching_callers_rows():
    """清单按色号排（排序规则见 test_codes_sort_naturally），但 materials() 的结果
    还要按用量排给网页用——render_legend 不能就地改掉调用方的列表。"""
    pal = _palette()
    rows = materials(_many_colors(), pal)
    before = [r["code"] for r in rows]
    render_legend(rows, pal, width=1600)
    assert [r["code"] for r in rows] == before


def test_downloaded_sheet_has_the_material_list_under_the_pattern():
    pal = _palette()
    g = _many_colors().repeat(3, axis=0)
    o = RenderOptions(cell_px=28)
    pattern = render_grid(g, pal, o)
    sheet = render_sheet(g, pal, o)
    assert sheet.width == pattern.width
    assert sheet.height > pattern.height + 28       # 底下多出一块清单
    # 上半截就是原来的图纸，一个像素都没动
    assert np.array_equal(np.asarray(sheet)[:pattern.height], np.asarray(pattern))


def test_sheet_widens_for_a_tiny_pattern_instead_of_clipping_the_list():
    pal = _palette()
    g = np.zeros((2, 2), dtype=np.int16)            # 图纸很窄，清单标题都比它宽
    sheet = render_sheet(g, pal, RenderOptions(cell_px=28))
    assert sheet.width >= render_legend(materials(g, pal), pal).width
