from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.core.merge import color_counts
from app.core.palette import Palette
from app.core.split import Board
from app.core.types import EMPTY

_LINE = (90, 90, 90)
_MAJOR = (30, 30, 30)
_EMPTY_BG = (245, 245, 245)
_EMPTY_HATCH = (215, 215, 215)
_HIGHLIGHT = (255, 0, 0)
_AXIS_BG = (255, 255, 255)


@dataclass
class RenderOptions:
    cell_px: int = 28
    show_codes: bool = True
    hide_empty_codes: bool = True
    hide_clear_codes: bool = False
    axis: bool = True
    minor_every: int = 5
    major_every: int = 10
    highlight: list[tuple[int, int]] = field(default_factory=list)
    board: Board | None = None


def text_color_for(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = rgb
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (0, 0, 0) if lum > 140 else (255, 255, 255)


def _font(size: int):
    """只用于纯 ASCII 的地方（格子里的色号、坐标轴）。它没有中文字形。"""
    try:
        return ImageFont.load_default(size=size)
    except TypeError:          # Pillow < 10.1
        return ImageFont.load_default()


_CJK_FONT_PATH = (Path(__file__).resolve().parents[1]
                  / "assets" / "fonts" / "fusion-pixel-12px-zh_hans-subset.ttf")


@lru_cache(maxsize=16)
def cjk_font(size: int):
    """带中文字形的字体，凡是要画汉字的地方都用它。

    Pillow 的默认字体没有中文：之前 PDF 材料清单里的"颗""包"、每页页脚的
    "第 1 行 / 第 1 列 页"一直渲染成方块，没人发现。

    这是像素字体（设计尺寸 12px），字号取 12 的整数倍才清楚，这里就近取整。
    协议 OFL 1.1，随附 OFL.txt。"""
    size = max(12, round(size / 12) * 12)
    try:
        return ImageFont.truetype(str(_CJK_FONT_PATH), size)
    except OSError:            # 字体文件丢了也别让导出整个失败，退回默认字体
        return _font(size)


def render_grid(grid: np.ndarray, palette: Palette, options: RenderOptions | None = None) -> Image.Image:
    o = options or RenderOptions()
    if o.board is not None:
        b = o.board
        grid = grid[b.row0:b.row0 + b.rows, b.col0:b.col0 + b.cols]
        row_off, col_off = b.row0, b.col0
    else:
        row_off = col_off = 0
    rows, cols = grid.shape
    cp = o.cell_px
    margin = int(cp * 0.9) if o.axis else 0
    W, H = cols * cp + 1 + margin, rows * cp + 1 + margin
    img = Image.new("RGB", (W, H), _AXIS_BG)
    d = ImageDraw.Draw(img)
    font = _font(max(6, int(cp * 0.4)))
    axis_font = _font(max(6, int(cp * 0.35)))
    clear_idx = palette.clear_index

    for r in range(rows):
        for c in range(cols):
            x0, y0 = margin + c * cp, margin + r * cp
            v = int(grid[r, c])
            if v == EMPTY:
                d.rectangle([x0, y0, x0 + cp, y0 + cp], fill=_EMPTY_BG)
                d.line([x0, y0 + cp, x0 + cp, y0], fill=_EMPTY_HATCH, width=1)
                continue
            rgb = tuple(int(x) for x in palette.rgb[v])
            d.rectangle([x0, y0, x0 + cp, y0 + cp], fill=rgb)
            if o.show_codes and not (o.hide_clear_codes and v == clear_idx):
                d.text((x0 + cp / 2, y0 + cp / 2), palette.codes[v],
                       fill=text_color_for(rgb), font=font, anchor="mm")

    for c in range(cols + 1):
        gc = c + col_off
        x = margin + c * cp
        major = bool(o.major_every) and gc % o.major_every == 0
        d.line([x, margin, x, margin + rows * cp], fill=_MAJOR if major else _LINE, width=2 if major else 1)
    for r in range(rows + 1):
        gr = r + row_off
        y = margin + r * cp
        major = bool(o.major_every) and gr % o.major_every == 0
        d.line([margin, y, margin + cols * cp, y], fill=_MAJOR if major else _LINE, width=2 if major else 1)

    if o.axis:
        for c in range(cols):
            gc = c + col_off
            # 最后一列也标：只标 1、6、11…的话，58 宽的图最后一个数是 56，读不出到底多宽
            if o.minor_every and (gc % o.minor_every == 0 or c == 0 or c == cols - 1):
                d.text((margin + c * cp + cp / 2, margin / 2), str(gc + 1),
                       fill=_MAJOR, font=axis_font, anchor="mm")
        for r in range(rows):
            gr = r + row_off
            if o.minor_every and (gr % o.minor_every == 0 or r == 0 or r == rows - 1):
                d.text((margin / 2, margin + r * cp + cp / 2), str(gr + 1),
                       fill=_MAJOR, font=axis_font, anchor="mm")

    for (r, c) in o.highlight:
        r -= row_off
        c -= col_off
        if 0 <= r < rows and 0 <= c < cols:
            x0, y0 = margin + c * cp, margin + r * cp
            d.rectangle([x0 + 1, y0 + 1, x0 + cp - 1, y0 + cp - 1], outline=_HIGHLIGHT, width=2)
    return img


def materials(grid: np.ndarray, palette: Palette, pack_size: int = 1000) -> list[dict]:
    rows = []
    for idx, n in color_counts(grid).items():
        rows.append({"index": idx, "code": palette.codes[idx],
                     "hex": "#{:02X}{:02X}{:02X}".format(*palette.rgb[idx]),
                     "count": n, "packs": math.ceil(n / pack_size)})
    rows.sort(key=lambda r: -r["count"])
    return rows


def _code_key(code: str) -> tuple:
    """色号自然排序：A2 在 A10 前面。拿豆子时是按色号顺序去豆盒里翻的。"""
    m = re.fullmatch(r"([A-Za-z]+)(\d+)", code)
    return (m.group(1).upper(), int(m.group(2))) if m else (code, 0)


#: 默认按 5mm 的中豆算实物尺寸，和 PDF 的 1:1 打印（PdfOptions.bead_mm）一致
BEAD_MM = 5.0


def size_line(rows: int, cols: int, bead_mm: float = BEAD_MM) -> str:
    """「宽 58 × 高 44 格 · 实物 29.0 × 22.0 cm（按 5 mm 豆）」

    写明哪边是宽哪边是高：只写"58×44"，拼的人得猜哪个是横的。"""
    return (f"宽 {cols} × 高 {rows} 格 · 实物 {cols * bead_mm / 10:.1f} × "
            f"{rows * bead_mm / 10:.1f} cm（按 {bead_mm:g} mm 豆）")


def render_legend(rows: list[dict], palette: Palette, swatch_px: int = 28, font_px: int = 24,
                  width: int | None = None,
                  size: tuple[int, int, float] | None = None) -> Image.Image:
    """材料清单：标题行给总数，下面按色号顺序排成多列，每项是 色块 / 色号 / 颗数。

    - **按色号排，不按用量排。** 这张是拿去翻豆盒的清单，豆盒是按色号分格的，
      顺着色号走一遍就拿齐了。网页上那份按用量排，是给人看哪几个色号是大头的，用途不同。
    - 给了 width 就排成多列铺满，不给就单列。原来是一根 280px 的单列，
      拼到一千多像素宽的图纸下面，右边全是空白。
    - 颗数右对齐，扫一眼就能比大小。"""
    font = cjk_font(font_px)
    pad = max(8, swatch_px // 2)
    gap = max(6, swatch_px // 3)
    line_h = max(swatch_px, font_px) + gap

    items = sorted(rows, key=lambda r: _code_key(r["code"]))
    total = sum(r["count"] for r in items)
    title = f"材料清单　共 {total} 颗 · {len(items)} 色"
    # 尺寸行放在清单标题上面：size = (行数, 列数, 豆子毫米数)
    header = [size_line(*size)] if size else []
    lines = header + [title]

    code_w = max((font.getlength(r["code"]) for r in items), default=0)
    count_w = max((font.getlength(f'{r["count"]} 颗') for r in items), default=0)
    col_w = int(swatch_px + gap + code_w + gap * 2 + count_w + gap * 3)

    inner = (width - 2 * pad) if width else col_w
    cols = max(1, min(len(items) or 1, inner // col_w))
    n_rows = math.ceil(len(items) / cols) if items else 0

    text_line_h = font_px + gap
    title_h = text_line_h * len(lines) + gap
    W = width if width else col_w * cols + 2 * pad
    W = max(W, *(int(font.getlength(t)) + 2 * pad for t in lines), col_w + 2 * pad)
    H = pad + title_h + n_rows * line_h + pad

    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for k, text in enumerate(lines):
        d.text((pad, pad + k * text_line_h + font_px / 2), text, fill=(0, 0, 0),
               font=font, anchor="lm")
    y_line = pad + title_h - gap
    d.line([pad, y_line, W - pad, y_line], fill=_MAJOR, width=2)

    for i, r in enumerate(items):
        row, col = divmod(i, cols)          # 横着排，符合阅读顺序
        x = pad + col * col_w
        y = pad + title_h + row * line_h
        mid = y + max(swatch_px, font_px) / 2
        rgb = tuple(int(v) for v in palette.rgb[r["index"]])
        sy = mid - swatch_px / 2
        d.rectangle([x, sy, x + swatch_px, sy + swatch_px], fill=rgb, outline=_LINE)
        d.text((x + swatch_px + gap, mid), r["code"], fill=(0, 0, 0), font=font, anchor="lm")
        d.text((x + col_w - gap * 3, mid), f'{r["count"]} 颗', fill=(0, 0, 0),
               font=font, anchor="rm")
    return img


def render_sheet(grid: np.ndarray, palette: Palette,
                 options: RenderOptions | None = None, bead_mm: float = BEAD_MM) -> Image.Image:
    """下载用的整张：图纸在上，材料清单在下。拿着一张图就能去拿豆子、开始拼。"""
    o = options or RenderOptions()
    pattern = render_grid(grid, palette, o)
    region = grid
    if o.board is not None:
        b = o.board
        region = grid[b.row0:b.row0 + b.rows, b.col0:b.col0 + b.cols]
    # 清单字号跟着格子走，但要是 12 的整数倍（像素字体）且不小于 12
    font_px = 24 if o.cell_px >= 20 else 12
    legend = render_legend(materials(region, palette), palette,
                           swatch_px=o.cell_px, font_px=font_px, width=pattern.width,
                           size=(region.shape[0], region.shape[1], bead_mm))

    W = max(pattern.width, legend.width)
    sep = max(8, o.cell_px // 2)
    sheet = Image.new("RGB", (W, pattern.height + sep + legend.height), (255, 255, 255))
    sheet.paste(pattern, ((W - pattern.width) // 2, 0))
    sheet.paste(legend, (0, pattern.height + sep))
    return sheet
