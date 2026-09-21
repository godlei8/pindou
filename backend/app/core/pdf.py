from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from app.core.palette import Palette
from app.core.render import RenderOptions, cjk_font, materials, render_grid, render_legend
from app.core.split import Board

_PAGES_MM = {"A4": (210.0, 297.0), "A3": (297.0, 420.0)}


@dataclass
class PdfOptions:
    bead_mm: float = 5.0
    dpi: int = 300
    page: str = "A4"
    margin_mm: float = 10.0
    overlap_cells: int = 2
    show_codes: bool = True


def _mm(mm: float, dpi: int) -> int:
    return round(mm / 25.4 * dpi)


def page_layout(rows: int, cols: int, options: PdfOptions) -> tuple[int, int, int, int]:
    o = options
    cell_px = _mm(o.bead_mm, o.dpi)
    pw, ph = _PAGES_MM[o.page]
    margin = _mm(o.margin_mm, o.dpi)
    axis_px = int(cell_px * 0.9)
    usable_w = _mm(pw, o.dpi) - 2 * margin - axis_px
    usable_h = _mm(ph, o.dpi) - 2 * margin - axis_px - _mm(8, o.dpi)   # 页脚
    return cell_px, usable_w // cell_px, usable_h // cell_px, margin


def _crop_marks(d: ImageDraw.ImageDraw, W: int, H: int, m: int, dpi: int) -> None:
    L = _mm(5, dpi)
    for x, y in ((m, m), (W - m, m), (m, H - m), (W - m, H - m)):
        d.line([x - L, y, x + L, y], fill=(0, 0, 0), width=2)
        d.line([x, y - L, x, y + L], fill=(0, 0, 0), width=2)


def render_pages(grid: np.ndarray, palette: Palette, options: PdfOptions | None = None) -> list[Image.Image]:
    """合成全部页面（图纸分页 + 末页材料清单）。PDF 序列化见 render_pdf。"""
    o = options or PdfOptions()
    rows, cols = grid.shape
    cell_px, cw, ch, margin = page_layout(rows, cols, o)
    pw, ph = _PAGES_MM[o.page]
    W, H = _mm(pw, o.dpi), _mm(ph, o.dpi)
    step_w, step_h = max(1, cw - o.overlap_cells), max(1, ch - o.overlap_cells)
    n_w = 1 if cols <= cw else math.ceil((cols - o.overlap_cells) / step_w)
    n_h = 1 if rows <= ch else math.ceil((rows - o.overlap_cells) / step_h)
    # 页脚是中文。原来用的默认字体没有中文字形，"第 1 行 / 第 1 列 页"一直是方块
    font = cjk_font(_mm(3, o.dpi))
    pages: list[Image.Image] = []

    for i in range(n_h):
        for j in range(n_w):
            r0, c0 = i * step_h, j * step_w
            r1, c1 = min(rows, r0 + ch), min(cols, c0 + cw)
            tile = render_grid(grid, palette,
                               RenderOptions(cell_px=cell_px, show_codes=o.show_codes, axis=True,
                                             board=Board(r0, c0, r1 - r0, c1 - c0, "")))
            page = Image.new("RGB", (W, H), (255, 255, 255))
            page.paste(tile, (margin, margin))
            d = ImageDraw.Draw(page)
            _crop_marks(d, W, H, margin // 2, o.dpi)
            d.text((W // 2, H - margin // 2),
                   f"第 {i + 1} 行 / 第 {j + 1} 列 页 · 共 {n_h}×{n_w} 页 · "
                   f"起始格 (行 {r0 + 1}, 列 {c0 + 1}) · 每格 {o.bead_mm} mm",
                   fill=(0, 0, 0), font=font, anchor="mm")
            pages.append(page)

    # 清单页：色块做成和实物豆一样大（bead_mm），字号按打印出来约 3.5mm 算，铺满页宽
    legend = render_legend(materials(grid, palette), palette,
                           swatch_px=_mm(o.bead_mm, o.dpi), font_px=_mm(3.5, o.dpi),
                           width=W - 2 * margin, size=(rows, cols, o.bead_mm))
    lp = Image.new("RGB", (W, H), (255, 255, 255))
    lp.paste(legend, (margin, margin))
    pages.append(lp)
    return pages


def render_pdf(grid: np.ndarray, palette: Palette, options: PdfOptions | None = None) -> bytes:
    o = options or PdfOptions()
    pages = render_pages(grid, palette, o)
    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", resolution=o.dpi, save_all=True, append_images=pages[1:])
    return buf.getvalue()
