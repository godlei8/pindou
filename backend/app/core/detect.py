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
    gaps = np.diff(peaks)
    period = float(np.median(gaps))
    cv = float(np.std(gaps) / period) if period > 0 else 1.0
    if period < min_cell or cv > 0.15:
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
