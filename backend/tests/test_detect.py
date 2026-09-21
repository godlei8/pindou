import numpy as np

from app.core.detect import detect_pixel_grid


def _pixel_art(cells_h=12, cells_w=16, cell=8, seed=0):
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, size=(cells_h, cells_w, 3)) / 255.0
    big = np.repeat(np.repeat(small, cell, axis=0), cell, axis=1)
    rgba = np.concatenate([big, np.ones(big.shape[:2] + (1,))], axis=-1).astype(np.float32)
    return rgba


def test_detects_upscaled_pixel_art():
    info = detect_pixel_grid(_pixel_art(cell=8))
    assert info is not None
    assert abs(info.cell - 8) < 0.5
    assert (info.rows, info.cols) == (12, 16)


def test_detects_with_padding_offset():
    art = _pixel_art(cell=6)
    padded = np.zeros((art.shape[0] + 5, art.shape[1] + 3, 4), dtype=np.float32)
    padded[..., 3] = 1.0
    padded[5:, 3:] = art
    info = detect_pixel_grid(padded)
    assert info is not None and abs(info.cell - 6) < 0.5
    assert abs(info.offset_x - 3) < 1.0 and abs(info.offset_y - 5) < 1.0


def test_smooth_gradient_is_not_pixel_art():
    y, x = np.mgrid[0:120, 0:160]
    rgba = np.zeros((120, 160, 4), dtype=np.float32)
    rgba[..., 0] = x / 160.0
    rgba[..., 1] = y / 120.0
    rgba[..., 3] = 1.0
    assert detect_pixel_grid(rgba) is None


def test_noise_is_not_pixel_art(rng):
    rgba = np.concatenate([rng.random((100, 100, 3)), np.ones((100, 100, 1))], axis=-1).astype(np.float32)
    assert detect_pixel_grid(rgba) is None


# ---- 连着几格同色的像素画（2026-09-21）------------------------------------------------

def _bench(name):
    from pathlib import Path
    return (Path(__file__).parent / "fixtures" / "bench" / name).read_bytes()


def test_pixel_art_with_missing_grid_lines_is_detected():
    """四周留白、大色块的像素画：很多格线上没有颜色变化，边界间距是 12、24、36 混着。"""
    from app.core import detect, image_io
    info = detect.detect_pixel_grid(image_io.load_rgba(_bench("pixel_sprite.png")))
    assert info is not None and (info.rows, info.cols, info.cell) == (32, 32, 12.0)


def test_pixel_art_is_one_to_one_even_with_background_removed():
    from app.core import pipeline
    from app.core.palette import Palette
    from app.core.types import EMPTY, Params
    res = pipeline.run(_bench("pixel_sprite.png"), Params(remove_background=True), Palette.load("mard"))
    assert res.input_kind == "pixel_art" and res.grid.shape == (32, 32)
    assert res.grid[0, 0] == EMPTY                       # 背景去掉了
    assert len(res.color_stats) == 6                     # 原图 6 种颜色一种不少（嘴只有 10 格也不并掉）


import pytest  # noqa: E402


@pytest.mark.parametrize("name", ["flat_chibi_face.png", "flat_thin_lineart.png", "photo_landscape.png",
                                  "soft_shaded.png", "flat_logo_text.png"])
def test_ordinary_images_are_not_mistaken_for_pixel_art(name):
    from app.core import detect, image_io
    assert detect.detect_pixel_grid(image_io.load_rgba(_bench(name))) is None
