from __future__ import annotations

import math
from dataclasses import dataclass, field

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
    try:
        return ImageFont.load_default(size=size)
    except TypeError:          # Pillow < 10.1
        return ImageFont.load_default()


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
            if o.minor_every and (gc % o.minor_every == 0 or c == 0):
                d.text((margin + c * cp + cp / 2, margin / 2), str(gc + 1),
                       fill=_MAJOR, font=axis_font, anchor="mm")
        for r in range(rows):
            gr = r + row_off
            if o.minor_every and (gr % o.minor_every == 0 or r == 0):
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


def render_legend(rows: list[dict], palette: Palette, cell_px: int = 28) -> Image.Image:
    line_h = cell_px + 6
    W = cell_px * 10
    img = Image.new("RGB", (W, max(line_h, line_h * len(rows))), (255, 255, 255))
    d = ImageDraw.Draw(img)
    font = _font(max(8, int(cell_px * 0.45)))
    for i, row in enumerate(rows):
        y = i * line_h + 3
        rgb = tuple(int(x) for x in palette.rgb[row["index"]])
        d.rectangle([3, y, 3 + cell_px, y + cell_px], fill=rgb, outline=_LINE)
        d.text((3 + cell_px + 8, y + cell_px / 2),
               f'{row["code"]}   {row["count"]} 颗   {row["packs"]} 包',
               fill=(0, 0, 0), font=font, anchor="lm")
    return img
