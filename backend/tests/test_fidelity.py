"""还原度：第一优先的指标。它得分得出"像"和"不像"——尤其是可拼性分不出来的那几种不像。"""
from pathlib import Path

import numpy as np
import pytest

from app.core import fidelity, flat, pipeline
from app.core.image_io import load_rgba
from app.core.palette import Palette
from app.core.types import EMPTY, Params
from tests.test_flat_outline import INK, ORANGE, WHITE, cat_png, code_of

PARAMS = Params(remove_background=True)


@pytest.fixture(scope="module")
def pal():
    return Palette.load("mard")


@pytest.fixture(scope="module")
def cat(pal):
    png = cat_png()
    res = pipeline.run(png, PARAMS, pal)
    rgba = pipeline._prepare(png, PARAMS)
    return res, rgba, flat.detect_inks(rgba)


def _score(cat, pal, grid):
    _, rgba, inks = cat
    return fidelity.measure(rgba, grid, pal.rgb, inks)["score"]


def test_pipeline_reports_fidelity(cat):
    res, _, _ = cat
    assert res.fidelity["method"] == "flat" and 70 < res.fidelity["score"] <= 100


def test_a_broken_outline_scores_lower(cat, pal):
    res, _, _ = cat
    g = res.grid.copy()
    ink, orange = code_of(pal, INK), code_of(pal, ORANGE)
    rows = np.where((g == ink).any(1))[0]
    for r in rows[5:-5:3]:                               # 每隔几行把左边的描边换成橙色
        g[r, int(np.argmax(g[r] == ink))] = orange
    assert _score(cat, pal, g) < res.fidelity["score"] - 1


def test_missing_highlights_score_lower(cat, pal):
    res, _, _ = cat
    g = res.grid.copy()
    g[g == code_of(pal, WHITE)] = code_of(pal, INK)
    assert _score(cat, pal, g) < res.fidelity["score"] - 0.5


def test_transition_colors_score_lower_than_clean_colors(cat, pal, monkeypatch):
    """「模糊后逐点比颜色」的指标会给混色更高的分——这个指标不能那样。"""
    res, _, _ = cat
    monkeypatch.setattr(flat, "detect_inks", lambda rgba: None)
    mixed = pipeline.run(cat_png(), PARAMS, pal)
    assert len(mixed.color_stats) > len(res.color_stats)
    assert _score(cat, pal, mixed.grid) < res.fidelity["score"] - 5


def test_wrong_color_scores_lower(cat, pal):
    res, _, _ = cat
    g = res.grid.copy()
    g[g == code_of(pal, ORANGE)] = code_of(pal, (255, 219, 77))
    assert _score(cat, pal, g) < res.fidelity["score"] - 10


def test_more_cells_means_higher_fidelity(pal):
    low = pipeline.run(cat_png(), Params(grid_long_side=30, remove_background=True), pal)
    high = pipeline.run(cat_png(), Params(grid_long_side=90, remove_background=True), pal)
    assert high.fidelity["score"] > low.fidelity["score"]


def test_photos_use_the_blur_method(pal):
    png = (Path(__file__).parent / "fixtures" / "images" / "photo_like.png").read_bytes()
    res = pipeline.run(png, Params(), pal)
    assert res.fidelity["method"] == "blur" and 0 < res.fidelity["score"] <= 100


def test_smoothing_never_costs_fidelity_on_flat_art(pal):
    """还原度第一：平整度 λ 在平涂图上不能拿还原度换可拼性。"""
    scores = [pipeline.run(cat_png(), Params(remove_background=True, smoothness=lam),
                           pal).fidelity["score"] for lam in (0.0, 2.0, 8.0)]
    assert scores[1] >= scores[0] and scores[2] >= scores[0]


def test_empty_grid_has_no_fidelity(pal):
    assert fidelity.measure(load_rgba(cat_png()), np.full((5, 5), EMPTY, np.int16), pal.rgb) is None


def test_measure_fidelity_for_an_existing_grid(cat, pal):
    res, _, _ = cat
    assert pipeline.measure_fidelity(cat_png(), PARAMS, res.grid, pal) == res.fidelity
