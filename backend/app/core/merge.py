from __future__ import annotations

import numpy as np
from scipy import ndimage

from app.core.color import pairwise_delta_e, srgb_to_oklab
from app.core.types import EMPTY

_CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)


def color_counts(grid: np.ndarray) -> dict[int, int]:
    vals, counts = np.unique(grid[grid != EMPTY], return_counts=True)
    return {int(v): int(c) for v, c in zip(vals, counts)}


def merge_small_colors(grid: np.ndarray, palette_lab: np.ndarray, threshold: int,
                       protected: set[int] = frozenset()) -> tuple[np.ndarray, list[tuple[int, int, float]]]:
    out = grid.copy()
    log: list[tuple[int, int, float]] = []
    while True:
        counts = color_counts(out)
        small = sorted((c for c, n in counts.items() if n < threshold and c not in protected),
                       key=lambda c: counts[c])
        if not small:
            break
        src = small[0]
        others = [c for c in counts if c != src]
        if not others:
            break
        d = pairwise_delta_e(palette_lab[[src]], palette_lab[others])[0]
        j = int(np.argmin(d))
        dst = others[j]
        out[out == src] = dst
        log.append((int(src), int(dst), float(d[j])))
    return out, log


def detect_outline_cells(cell_rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    ok = srgb_to_oklab(cell_rgb)
    dark = (ok[..., 0] < 0.35) & (np.hypot(ok[..., 1], ok[..., 2]) < 0.06) & mask
    thick = ndimage.binary_erosion(dark, structure=_CROSS, border_value=0)
    thin = dark & ~ndimage.binary_dilation(thick, structure=_CROSS)
    return thin
