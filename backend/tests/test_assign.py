import numpy as np

from app.core.assign import assign_labels, energy


def _two_color_cost(rows, cols, split_col, noise_cells=()):
    """左半偏好 0，右半偏好 1；noise_cells 里的格子偏好被反转（模拟散点）。"""
    cost = np.zeros((rows, cols, 2))
    cost[:, :split_col, 1] = 10.0
    cost[:, split_col:, 0] = 10.0
    for r, c in noise_cells:
        cost[r, c] = cost[r, c][::-1]
    return cost


def test_lambda_zero_is_pure_argmin():
    cost = _two_color_cost(6, 8, 4, noise_cells=[(2, 1)])
    mask = np.ones((6, 8), bool)
    out = assign_labels(cost, mask, smoothness=0.0)
    assert out[2, 1] == 1                      # 散点保留
    assert out[0, 0] == 0 and out[0, 7] == 1


def test_smoothness_removes_isolated_noise_but_keeps_real_edge():
    cost = _two_color_cost(6, 8, 4, noise_cells=[(2, 1)])
    mask = np.ones((6, 8), bool)
    out = assign_labels(cost, mask, smoothness=4.0)   # 4 条边 × λ=4 = 16 > 10 的数据代价
    assert out[2, 1] == 0                      # 散点被平滑掉
    assert (out[:, :4] == 0).all() and (out[:, 4:] == 1).all()   # 真实边界保留


def test_masked_cells_are_minus_one_and_do_not_connect():
    cost = _two_color_cost(3, 3, 1)
    mask = np.ones((3, 3), bool)
    mask[1, 1] = False
    out = assign_labels(cost, mask, smoothness=100.0)
    assert out[1, 1] == -1
    assert set(out[mask].tolist()) <= {0, 1}


def test_locked_cells_are_respected():
    cost = _two_color_cost(4, 4, 2)
    mask = np.ones((4, 4), bool)
    locked = -np.ones((4, 4), int)
    locked[0, 0] = 1
    out = assign_labels(cost, mask, smoothness=0.0, locked=locked)
    assert out[0, 0] == 1


def test_energy_never_increases_vs_argmin_baseline(rng):
    cost = rng.random((20, 20, 6)) * 10
    mask = rng.random((20, 20)) > 0.1
    base = np.where(mask, cost.argmin(axis=-1), -1)
    out = assign_labels(cost, mask, smoothness=2.0)
    assert energy(cost, mask, out, 2.0) <= energy(cost, mask, base, 2.0) + 1e-6


def test_runs_fast_enough_for_interactive_use():
    import time
    rng = np.random.default_rng(3)
    cost = rng.random((100, 100, 40)) * 10
    mask = np.ones((100, 100), bool)
    t = time.perf_counter()
    assign_labels(cost, mask, smoothness=1.5, n_sweeps=2)
    assert time.perf_counter() - t < 3.0
