import numpy as np
from PIL import Image

from app.core.palette import Palette
from app.core.render import RenderOptions, materials, render_grid, render_legend, text_color_for
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
