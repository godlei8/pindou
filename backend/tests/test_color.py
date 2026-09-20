import numpy as np
import pytest

from app.core import color


def test_srgb_linear_roundtrip():
    x = np.linspace(0, 1, 101)
    assert np.allclose(color.linear_to_srgb(color.srgb_to_linear(x)), x, atol=1e-6)


def test_srgb_to_linear_known_values():
    # sRGB 0.5 → 线性 0.214041
    assert abs(color.srgb_to_linear(np.array(0.5)) - 0.214041) < 1e-5
    assert color.srgb_to_linear(np.array(0.0)) == 0.0
    assert abs(color.srgb_to_linear(np.array(1.0)) - 1.0) < 1e-9


def test_srgb_to_lab_white_black_and_red():
    lab = color.srgb_to_lab(np.array([[1.0, 1.0, 1.0], [0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]))
    assert np.allclose(lab[0], [100.0, 0.0, 0.0], atol=0.05)
    assert np.allclose(lab[1], [0.0, 0.0, 0.0], atol=0.05)
    # 纯红 sRGB → Lab(53.24, 80.09, 67.20)（D65）
    assert np.allclose(lab[2], [53.24, 80.09, 67.20], atol=0.1)


def test_srgb_to_oklab_white_and_red():
    ok = color.srgb_to_oklab(np.array([[1.0, 1.0, 1.0], [1.0, 0.0, 0.0]]))
    assert np.allclose(ok[0], [1.0, 0.0, 0.0], atol=1e-3)
    # Ottosson 参考：红 → L=0.628, a=0.225, b=0.126
    assert np.allclose(ok[1], [0.628, 0.225, 0.126], atol=2e-3)


def test_shapes_preserved():
    img = np.zeros((4, 5, 3))
    assert color.srgb_to_lab(img).shape == (4, 5, 3)
    assert color.srgb_to_oklab(img).shape == (4, 5, 3)


from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _load_sharma():
    rows = []
    for line in (FIXTURES / "ciede2000_testdata.txt").read_text().splitlines():
        parts = line.split()
        if len(parts) >= 7:
            rows.append([float(p) for p in parts[:7]])
    return np.array(rows)


def test_ciede2000_matches_sharma_34_pairs():
    data = _load_sharma()
    assert len(data) == 34
    lab1, lab2, expected = data[:, 0:3], data[:, 3:6], data[:, 6]
    got = color.delta_e_2000(lab1, lab2)
    assert np.allclose(got, expected, atol=1e-4), np.c_[got, expected]


def test_ciede2000_is_symmetric_and_zero_on_identity():
    a = np.array([[50.0, 2.5, 0.0], [20.0, -30.0, 40.0]])
    b = np.array([[73.0, 25.0, -18.0], [21.0, -29.0, 41.0]])
    assert np.allclose(color.delta_e_2000(a, b), color.delta_e_2000(b, a))
    assert np.allclose(color.delta_e_2000(a, a), 0.0)


def test_pairwise_delta_e_shape_and_broadcast():
    a = np.random.default_rng(1).uniform([0, -80, -80], [100, 80, 80], size=(7, 3))
    b = np.random.default_rng(2).uniform([0, -80, -80], [100, 80, 80], size=(5, 3))
    m = color.pairwise_delta_e(a, b)
    assert m.shape == (7, 5)
    assert np.allclose(m[3, 2], color.delta_e_2000(a[3], b[2]))
