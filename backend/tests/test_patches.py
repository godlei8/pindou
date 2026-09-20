import numpy as np

from app.core.buildability import analyze
from app.core.patches import apply_patch, attach_patches

LAB = np.array([[50, 0, 0], [80, 0, 0], [20, 0, 0], [95, 0, 0]], dtype=float)
CLEAR = 3


def _report(grid):
    return attach_patches(analyze(grid, LAB, small_color_threshold=3), grid, CLEAR)


def _first(report, t):
    return next(i for i in report.issues if i.type == t)


def test_isolated_bead_with_diagonal_neighbor_gets_clear_bridge():
    g = np.full((5, 5), -1, dtype=np.int16)
    g[2, 2] = 0
    g[3, 3] = 0; g[3, 4] = 0; g[4, 3] = 0; g[4, 4] = 0
    issue = _first(_report(g), "isolated_bead")
    assert issue.action == "bridge_with_clear"
    assert issue.patch_cells in ([(2, 3)], [(3, 2)])
    out = apply_patch(g, issue, CLEAR)
    assert analyze(out, LAB).n_components == 1
    assert out[tuple(issue.patch_cells[0])] == CLEAR


def test_truly_isolated_bead_is_removed():
    g = np.full((5, 5), -1, dtype=np.int16)
    g[0, 0] = 0
    g[4, 4] = 0; g[4, 3] = 0; g[3, 4] = 0; g[3, 3] = 0
    issue = _first(_report(g), "isolated_bead")
    assert issue.action == "remove"
    assert apply_patch(g, issue, CLEAR)[0, 0] == -1


def test_diagonal_link_bridge_connects():
    g = np.full((4, 4), -1, dtype=np.int16)
    g[0, 0] = 0; g[1, 1] = 0
    issue = _first(_report(g), "diagonal_link")
    out = apply_patch(g, issue, CLEAR)
    assert analyze(out, LAB).metrics["n_diagonal"] == 0
    assert (out == CLEAR).sum() == 1


def test_thin_line_thickened_with_clear():
    g = np.full((7, 7), -1, dtype=np.int16)
    g[3, :] = 0
    issue = _first(_report(g), "thin_line")
    out = apply_patch(g, issue, CLEAR)
    assert analyze(out, LAB).metrics["thin_ratio"] < 0.5
    assert (out == 0).sum() == 7


def test_hole_filled_with_clear():
    g = np.zeros((5, 5), dtype=np.int16)
    g[2, 2] = -1
    issue = _first(_report(g), "hole")
    assert issue.action == "fill_with_clear"
    assert apply_patch(g, issue, CLEAR)[2, 2] == CLEAR


def test_small_color_merged():
    g = np.zeros((5, 5), dtype=np.int16)
    g[0, 0] = 2
    issue = _first(_report(g), "small_color")
    assert issue.action == "merge_color" and issue.target_color == 0
    assert (apply_patch(g, issue, CLEAR) == 2).sum() == 0


def test_disconnected_component_bridged_by_shortest_path():
    g = np.full((3, 9), -1, dtype=np.int16)
    g[1, 0:2] = 0
    g[1, 6:9] = 1
    issue = _first(_report(g), "disconnected")
    assert issue.action == "bridge_with_clear"
    assert sorted(issue.patch_cells) == [(1, 2), (1, 3), (1, 4), (1, 5)]
    assert analyze(apply_patch(g, issue, CLEAR), LAB).n_components == 1


def test_without_clear_index_bridges_degrade_to_remove():
    g = np.full((4, 4), -1, dtype=np.int16)
    g[0, 0] = 0; g[1, 1] = 0
    r = attach_patches(analyze(g, LAB), g, None)
    assert all(i.action in ("remove", "none", "merge_color") for i in r.issues)


def test_apply_does_not_mutate_input():
    g = np.zeros((5, 5), dtype=np.int16)
    g[2, 2] = -1
    before = g.copy()
    apply_patch(g, _first(_report(g), "hole"), CLEAR)
    assert np.array_equal(g, before)
