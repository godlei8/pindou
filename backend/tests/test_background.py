import numpy as np

from app.core.background import remove_background


def _canvas(h=20, w=20):
    rgba = np.zeros((h, w, 4), dtype=np.float32)
    rgba[..., :3] = 1.0
    rgba[..., 3] = 1.0
    rgba[5:15, 5:15, :3] = [1.0, 0.0, 0.0]
    return rgba


def test_flood_from_corner_clears_only_connected_background():
    out = remove_background(_canvas(), seed_xy=(0, 0), tolerance=0.05)
    assert out[0, 0, 3] == 0.0 and out[19, 19, 3] == 0.0
    assert out[10, 10, 3] == 1.0 and out[10, 10, 0] == 1.0


def test_enclosed_region_not_touched_by_outer_flood():
    rgba = _canvas()
    rgba[8:12, 8:12, :3] = 1.0
    out = remove_background(rgba, seed_xy=(0, 0), tolerance=0.05)
    assert out[10, 10, 3] == 1.0


def test_tolerance_controls_spread():
    rgba = _canvas()
    rgba[0:20, 0:3, :3] = [0.97, 0.97, 0.97]
    strict = remove_background(rgba, seed_xy=(19, 19), tolerance=0.01)
    loose = remove_background(rgba, seed_xy=(19, 19), tolerance=0.1)
    assert strict[10, 1, 3] == 1.0
    assert loose[10, 1, 3] == 0.0


def test_input_not_mutated():
    rgba = _canvas()
    before = rgba.copy()
    remove_background(rgba, seed_xy=(0, 0))
    assert np.array_equal(rgba, before)
