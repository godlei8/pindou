from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageOps


def load_rgba(data: bytes, max_side: int = 1024) -> np.ndarray:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGBA")
    w, h = img.size
    scale = max(w, h) / max_side
    if scale > 1.0:
        img = img.resize((max(1, round(w / scale)), max(1, round(h / scale))), Image.BOX)
    return np.ascontiguousarray(np.asarray(img, dtype=np.float32) / 255.0)


def to_pil(rgba: np.ndarray) -> Image.Image:
    arr8 = np.clip(np.rint(rgba * 255.0), 0, 255).astype(np.uint8)
    return Image.fromarray(arr8, mode="RGBA")
