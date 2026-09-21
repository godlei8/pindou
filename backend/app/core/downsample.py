from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.core.color import linear_to_srgb, srgb_to_linear
from app.core.detect import GridInfo


@dataclass
class CellImage:
    rgb: np.ndarray
    coverage: np.ndarray
    mask: np.ndarray
    #: 平涂取色（core/flat.py）出来的：每格的颜色都是这几种墨之一（sRGB 0–1），没有过渡色。
    #: 面积平均出来的（照片）是 None
    inks: np.ndarray | None = None

    @property
    def flat(self) -> bool:
        return self.inks is not None


def grid_shape(h: int, w: int, long_side: int) -> tuple[int, int]:
    if w >= h:
        cols = long_side
        rows = max(1, round(long_side * h / w))
    else:
        rows = long_side
        cols = max(1, round(long_side * w / h))
    return rows, cols


def _bilateral(rgb: np.ndarray) -> np.ndarray:
    return cv2.bilateralFilter(rgb.astype(np.float32), d=7, sigmaColor=0.1, sigmaSpace=5)


def downsample_area(rgba: np.ndarray, rows: int, cols: int, denoise: bool = True) -> CellImage:
    rgb = rgba[..., :3].astype(np.float32)
    alpha = rgba[..., 3].astype(np.float32)
    if denoise:
        rgb = _bilateral(rgb)
    lin = srgb_to_linear(rgb).astype(np.float32)
    premul = lin * alpha[..., None]
    small_premul = cv2.resize(premul, (cols, rows), interpolation=cv2.INTER_AREA)
    coverage = cv2.resize(alpha, (cols, rows), interpolation=cv2.INTER_AREA)
    small_premul = small_premul.reshape(rows, cols, 3)
    coverage = coverage.reshape(rows, cols)
    safe = np.where(coverage > 1e-6, coverage, 1.0)[..., None]
    small_lin = small_premul / safe
    out_rgb = linear_to_srgb(small_lin).astype(np.float32)
    mask = coverage >= 0.5
    return CellImage(rgb=out_rgb, coverage=coverage.astype(np.float32), mask=mask)


def downsample_mode(rgba: np.ndarray, grid: GridInfo) -> CellImage:
    h, w = rgba.shape[:2]
    rgb8 = np.clip(np.rint(rgba[..., :3] * 255), 0, 255).astype(np.int64)
    key = (rgb8[..., 0] << 16) | (rgb8[..., 1] << 8) | rgb8[..., 2]
    alpha = rgba[..., 3]
    out = np.zeros((grid.rows, grid.cols, 3), dtype=np.float32)
    cov = np.zeros((grid.rows, grid.cols), dtype=np.float32)
    for r in range(grid.rows):
        y0 = int(round(grid.offset_y + r * grid.cell))
        y1 = min(h, int(round(grid.offset_y + (r + 1) * grid.cell)))
        for c in range(grid.cols):
            x0 = int(round(grid.offset_x + c * grid.cell))
            x1 = min(w, int(round(grid.offset_x + (c + 1) * grid.cell)))
            if y1 <= y0 or x1 <= x0:
                continue
            block_a = alpha[y0:y1, x0:x1]
            cov[r, c] = float(block_a.mean())
            opaque = block_a >= 0.5
            if not opaque.any():
                continue
            vals, counts = np.unique(key[y0:y1, x0:x1][opaque], return_counts=True)
            k = int(vals[counts.argmax()])
            out[r, c] = [(k >> 16) & 255, (k >> 8) & 255, k & 255]
    return CellImage(rgb=out / 255.0, coverage=cov, mask=cov >= 0.5)
