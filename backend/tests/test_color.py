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
