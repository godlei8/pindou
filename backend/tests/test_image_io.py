import io

import numpy as np
from PIL import Image

from app.core.image_io import load_rgba, to_pil


def _png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_load_rgb_png_becomes_float_rgba():
    arr = load_rgba(_png_bytes(Image.new("RGB", (40, 20), (255, 0, 0))))
    assert arr.shape == (20, 40, 4) and arr.dtype == np.float32
    assert np.allclose(arr[0, 0], [1, 0, 0, 1])


def test_load_preserves_alpha():
    arr = load_rgba(_png_bytes(Image.new("RGBA", (10, 10), (0, 0, 255, 0))))
    assert arr[..., 3].max() == 0.0


def test_load_downsizes_long_side_but_never_upsizes():
    arr = load_rgba(_png_bytes(Image.new("RGB", (3000, 1500), (10, 20, 30))), max_side=1024)
    assert arr.shape[1] == 1024 and arr.shape[0] == 512
    assert load_rgba(_png_bytes(Image.new("RGB", (100, 50), (1, 2, 3)))).shape[:2] == (50, 100)


def test_load_applies_exif_orientation():
    img = Image.new("RGB", (40, 20), (0, 255, 0))
    exif = img.getexif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    assert load_rgba(buf.getvalue()).shape[:2] == (40, 20)


def test_to_pil_roundtrip():
    arr = np.zeros((5, 6, 4), dtype=np.float32)
    arr[..., 0] = 1.0
    arr[..., 3] = 1.0
    pil = to_pil(arr)
    assert pil.mode == "RGBA" and pil.size == (6, 5) and pil.getpixel((0, 0)) == (255, 0, 0, 255)
