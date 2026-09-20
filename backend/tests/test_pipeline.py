import json
from pathlib import Path

import numpy as np
import pytest

from app.core import pipeline
from app.core.color import pairwise_delta_e
from app.core.palette import Palette
from app.core.types import EMPTY, Params

IMG = Path(__file__).parent / "fixtures" / "images"
SNAP = Path(__file__).parent / "fixtures" / "snapshots"
SNAP.mkdir(exist_ok=True)


@pytest.fixture(scope="module")
def palette():
    return Palette.load("mard")


def _run(name, **kw):
    return pipeline.run((IMG / name).read_bytes(), Params(**kw))


def test_cartoon_end_to_end(palette):
    res = _run("cartoon.png", grid_long_side=48, max_colors=8)
    assert res.grid.shape == (48, 48) and res.grid.dtype == np.int16
    assert res.input_kind == "image"
    assert 3 <= len(res.working_palette) <= 8
    assert res.report is not None and res.report.score > 60
    # 十字绣领域的标定：<2% 理想，>10% 极难做。带抗锯齿的细描边圆弧天生是
    # 对角阶梯，注定偏高；这里守住"可拼"这条线，具体数值靠 λ 调。
    assert res.report.confetti_pct < 10


def test_raising_lambda_measurably_reduces_confetti_on_cartoon(palette):
    """λ 是散点的有效杠杆——这条比任何绝对阈值都更能说明算法在起作用。"""
    low = _run("cartoon.png", grid_long_side=48, max_colors=8, smoothness=0.0)
    high = _run("cartoon.png", grid_long_side=48, max_colors=8, smoothness=4.0)
    assert high.report.confetti_pct < low.report.confetti_pct - 2.0
    assert high.report.confetti_pct < 4.0


def test_pixel_art_is_detected_and_reproduced_exactly(palette):
    res = _run("pixel_art.png", grid_long_side=58, max_colors=8)
    assert res.input_kind == "pixel_art"
    assert res.grid.shape == (16, 16)
    assert len(res.working_palette) == 4


def test_lambda_zero_equals_nearest_color(palette):
    res = _run("logo.png", grid_long_side=30, max_colors=6, smoothness=0.0)
    lab = pipeline._cell_lab(res.cell_rgb)
    sub = palette.lab[res.working_palette]
    nearest = np.array(res.working_palette)[
        pairwise_delta_e(lab.reshape(-1, 3), sub).argmin(1)].reshape(res.grid.shape)
    mask = res.grid != EMPTY
    assert (res.grid[mask] == nearest[mask]).mean() > 0.97


def test_smoothness_reduces_confetti_on_noisy_photo(palette):
    a = _run("photo_like.png", grid_long_side=50, max_colors=12, smoothness=0.0, lock_outlines=False)
    b = _run("photo_like.png", grid_long_side=50, max_colors=12, smoothness=2.0, lock_outlines=False)
    assert b.report.confetti_pct < a.report.confetti_pct


def test_transparent_png_yields_empty_cells_not_black_or_white(palette):
    res = _run("transparent.png", grid_long_side=30, max_colors=4)
    assert res.grid[0, 0] == EMPTY
    center = res.grid[15, 15]
    assert center != EMPTY and palette.lab[center, 1] > 20        # 偏红


def test_wide_image_keeps_aspect(palette):
    res = _run("wide.png", grid_long_side=60, max_colors=4)
    assert res.grid.shape == (20, 60)


def test_gray_stays_neutral_and_yellow_stays_yellow(palette):
    g = _run("gray_object.png", grid_long_side=30, max_colors=4)
    c = g.grid[15, 15]
    assert abs(palette.lab[c, 1]) < 8 and abs(palette.lab[c, 2]) < 8
    y = _run("yellow_object.png", grid_long_side=30, max_colors=4)
    c = y.grid[15, 15]
    assert palette.lab[c, 2] > 30 and palette.lab[c, 1] > -15


def test_solid_block_interior_is_filled(palette):
    res = _run("solid_block.png", grid_long_side=30, max_colors=4)
    inner = res.grid[10:20, 10:20]
    assert (inner != EMPTY).all() and len(np.unique(inner)) == 1


def test_suggest_sizes_returns_three_ordered_options():
    s = pipeline.suggest_sizes((IMG / "cartoon.png").read_bytes(), base=58)
    assert [x["long_side"] for x in s] == [44, 58, 87]
    assert s[0]["detail_loss"] >= s[1]["detail_loss"] >= s[2]["detail_loss"]


def test_apply_edits_rewrites_cells_and_reanalyzes(palette):
    res = _run("logo.png", grid_long_side=30, max_colors=6)
    target = int(res.working_palette[0])
    out = pipeline.apply_edits(res, [(0, 0, target), (1, 1, -1)], palette)
    assert out.grid[0, 0] == target and out.grid[1, 1] == EMPTY
    assert out.report is not None
    assert not np.shares_memory(out.grid, res.grid)


@pytest.mark.parametrize("name", ["cartoon.png", "logo.png", "pixel_art.png", "diagonal_trap.png"])
def test_golden_snapshot(name, palette):
    res = _run(name, grid_long_side=40, max_colors=8)
    snap = SNAP / f"{name}.json"
    current = res.grid_as_list()
    if not snap.exists():
        snap.write_text(json.dumps(current))
        pytest.skip("snapshot created")
    old = json.loads(snap.read_text())
    diff = sum(a != b for ra, rb in zip(old, current) for a, b in zip(ra, rb))
    assert diff <= 0.02 * res.grid.size, f"{name}: {diff} cells changed vs snapshot"
