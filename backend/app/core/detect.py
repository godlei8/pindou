from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks


@dataclass
class GridInfo:
    cell: float
    offset_x: float
    offset_y: float
    cols: int
    rows: int
    confidence: float


def _axis_period(signal: np.ndarray, min_cell: int) -> tuple[float, float, float] | None:
    """返回 (period, offset, cv)；找不到规律返回 None。"""
    if signal.size < 2 * min_cell + 1:
        return None
    med = float(np.median(signal))
    peaks, _ = find_peaks(signal, prominence=max(med * 2.0, 1e-6), distance=min_cell - 1)
    if len(peaks) < 3:
        return None
    # 找一个周期，让（几乎）所有边界都落在同一张网格上。不能要求"相邻边界的间距都一样"：
    # 像素画里连着几格同色很常见（四周留白、大色块），那几条边界不存在，间距会是 12、24、36 混着。
    gaps = np.diff(peaks)
    period = None
    for cand in np.unique(gaps[gaps >= min_cell]):
        res = (peaks - peaks[0]) % cand
        # 容差按周期算：周期只有 3 像素时容差不能有 1，否则任何位置都"对得上"
        off_grid = np.minimum(res, cand - res) > np.floor(0.08 * cand)
        # 边界还得够多：一个纯色物体只有左右两条边，随便什么周期都"对得上"，那不是像素画
        if off_grid.mean() <= 0.1 and len(peaks) >= max(4, 0.3 * signal.size / cand):
            period, cv = float(cand), float(off_grid.mean())
            break
    if period is None:
        return None
    # 边界峰位于格子右/下边缘的最后一个像素之后（差分索引 i 对应像素 i 与 i+1 之间）
    offset = float(np.median((peaks + 1) % period))
    return period, offset, cv


def detect_pixel_grid(rgba: np.ndarray, min_cell: int = 3, max_cells: int = 200) -> GridInfo | None:
    rgb = rgba[..., :3]
    h, w = rgb.shape[:2]
    dx = np.abs(np.diff(rgb, axis=1)).sum(axis=-1).sum(axis=0)   # 长度 w-1，列边界
    dy = np.abs(np.diff(rgb, axis=0)).sum(axis=-1).sum(axis=1)   # 长度 h-1，行边界
    px = _axis_period(dx, min_cell)
    py = _axis_period(dy, min_cell)
    if px is None or py is None:
        return None
    cell = (px[0] + py[0]) / 2
    if abs(px[0] - py[0]) / cell > 0.1:
        return None
    ox, oy = px[1], py[1]
    cols = int(round((w - ox) / cell))
    rows = int(round((h - oy) / cell))
    if cols < 2 or rows < 2 or cols > max_cells or rows > max_cells:
        return None
    return GridInfo(cell=cell, offset_x=ox, offset_y=oy, cols=cols, rows=rows,
                    confidence=float(1.0 - (px[2] + py[2]) / 2))
