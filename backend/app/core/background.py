from __future__ import annotations

import numpy as np
from scipy import ndimage

from app.core.color import srgb_to_oklab

_CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])


def remove_background(rgba: np.ndarray, seed_xy: tuple[int, int], tolerance: float = 0.08) -> np.ndarray:
    x, y = int(seed_xy[0]), int(seed_xy[1])
    h, w = rgba.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        raise ValueError(f"seed {seed_xy} outside image {w}x{h}")
    ok = srgb_to_oklab(rgba[..., :3])
    within = np.linalg.norm(ok - ok[y, x], axis=-1) <= tolerance
    labels, _ = ndimage.label(within, structure=_CROSS)
    out = rgba.copy()
    out[labels == labels[y, x], 3] = 0.0
    return out
