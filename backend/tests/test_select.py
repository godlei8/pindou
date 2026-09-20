import numpy as np

from app.core.select import select_palette


def _palette():
    # 8 色：黑、白、红、绿、蓝、黄、以及两个很接近的红
    return np.array([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.63, 0.22, 0.13], [0.87, -0.23, 0.18],
        [0.45, -0.03, -0.31], [0.97, -0.07, 0.20], [0.64, 0.21, 0.12], [0.62, 0.23, 0.14],
    ])


def test_returns_palette_indices_and_at_most_k():
    cells = np.repeat(_palette()[[0, 1, 2]], 20, axis=0)
    idx = select_palette(cells, _palette(), k=3)
    assert set(idx.tolist()) == {0, 1, 2}
    assert len(idx) <= 3


def test_never_returns_duplicates_even_with_near_identical_palette_entries():
    cells = np.repeat(_palette()[[2]], 50, axis=0) + np.random.default_rng(0).normal(0, 0.005, (50, 3))
    idx = select_palette(cells, _palette(), k=4)
    assert len(idx) == len(set(idx.tolist()))
    assert len(idx) <= 4


def test_small_but_distinct_cluster_survives():
    # 190 格红 + 10 格白：频次截断会丢白，k-medoids 在 k=2 下必须保留白
    cells = np.concatenate([np.repeat(_palette()[[2]], 190, axis=0), np.repeat(_palette()[[1]], 10, axis=0)])
    idx = select_palette(cells, _palette(), k=2)
    assert 1 in idx.tolist()


def test_weights_bias_selection():
    cells = np.concatenate([np.repeat(_palette()[[3]], 10, axis=0), np.repeat(_palette()[[4]], 10, axis=0)])
    w = np.concatenate([np.ones(10) * 100.0, np.ones(10)])
    idx = select_palette(cells, _palette(), k=1, weights=w)
    assert idx.tolist() == [3]


def test_deterministic_with_seed(rng):
    cells = rng.random((200, 3))
    a = select_palette(cells, _palette(), k=5, seed=7)
    b = select_palette(cells, _palette(), k=5, seed=7)
    assert a.tolist() == b.tolist()
