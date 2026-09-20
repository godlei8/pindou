"""注意：Pillow 只能写 PDF、不能读，所以页面结构通过 render_pages 验证，
PDF 字节只做结构性抽查（页数、MediaBox 物理尺寸）。"""
import math
import re

import numpy as np

from app.core.palette import Palette
from app.core.pdf import PdfOptions, page_layout, render_pages, render_pdf


def _count_pdf_pages(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", data))


def test_cell_px_matches_physical_size():
    cell_px, cw, ch, margin = page_layout(10, 10, PdfOptions(bead_mm=5.0, dpi=300))
    assert cell_px == 59                       # 5 mm @ 300 dpi
    assert margin == round(10 / 25.4 * 300)
    # A4 可打印宽 190 mm，减去坐标轴留白后按格宽整除
    assert cw == (round(190 / 25.4 * 300) - int(cell_px * 0.9)) // 59


def test_small_grid_fits_one_page_plus_legend():
    g = np.zeros((10, 10), dtype=np.int16)
    pages = render_pages(g, Palette.load("mard"))
    assert len(pages) == 2                     # 1 页图纸 + 1 页清单
    data = render_pdf(g, Palette.load("mard"))
    assert data[:5] == b"%PDF-"
    assert _count_pdf_pages(data) == 2


def test_large_grid_paginates_with_overlap():
    g = np.zeros((80, 80), dtype=np.int16)
    opts = PdfOptions()
    _, cw, ch, _ = page_layout(80, 80, opts)
    step_w, step_h = cw - opts.overlap_cells, ch - opts.overlap_cells
    expect = (math.ceil((80 - opts.overlap_cells) / step_w)
              * math.ceil((80 - opts.overlap_cells) / step_h)) + 1
    assert len(render_pages(g, Palette.load("mard"), opts)) == expect
    assert expect > 2                          # 这个尺寸确实需要分页，否则测不到重叠逻辑


def test_page_is_a4_at_dpi():
    g = np.zeros((5, 5), dtype=np.int16)
    opts = PdfOptions(dpi=150)
    pages = render_pages(g, Palette.load("mard"), opts)
    w, h = pages[0].size
    assert abs(w / 150 * 25.4 - 210) < 1.0 and abs(h / 150 * 25.4 - 297) < 1.0
    # PDF 里的 MediaBox 用 pt（1/72 inch），A4 ≈ 595×842
    box = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)", render_pdf(g, Palette.load("mard"), opts))
    assert box is not None
    assert abs(float(box.group(1)) - 595) < 2 and abs(float(box.group(2)) - 842) < 2


def test_every_grid_page_carries_a_footer_and_crop_marks():
    g = np.zeros((80, 80), dtype=np.int16)
    pages = render_pages(g, Palette.load("mard"), PdfOptions(dpi=150))
    first = np.asarray(pages[0].convert("L"))
    # 四角对位标记：角落附近必有黑像素
    m = round(10 / 25.4 * 150) // 2
    assert first[m - 2:m + 3, m - 2:m + 3].min() < 50
    # 页脚区域有文字
    assert first[-m - 20:, :].min() < 100
