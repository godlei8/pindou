"""色彩空间转换。所有函数向量化，输入 sRGB 取值 0–1。"""
from __future__ import annotations

import numpy as np

_M_RGB2XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
])
_WHITE_D65 = np.array([0.95047, 1.0, 1.08883])

_M_RGB2LMS = np.array([
    [0.4122214708, 0.5363325363, 0.0514459929],
    [0.2119034982, 0.6806995451, 0.1073969566],
    [0.0883024619, 0.2817188376, 0.6299787005],
])
_M_LMS2OKLAB = np.array([
    [0.2104542553, 0.7936177850, -0.0040720468],
    [1.9779984951, -2.4285922050, 0.4505937099],
    [0.0259040371, 0.7827717662, -0.8086757660],
])


def srgb_to_linear(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(np.asarray(x, dtype=np.float64), 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    lin = srgb_to_linear(rgb)
    xyz = lin @ _M_RGB2XYZ.T
    t = xyz / _WHITE_D65
    delta = 6 / 29
    f = np.where(t > delta ** 3, np.cbrt(t), t / (3 * delta ** 2) + 4 / 29)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def srgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    lin = srgb_to_linear(rgb)
    lms = lin @ _M_RGB2LMS.T
    lms_ = np.cbrt(lms)
    return lms_ @ _M_LMS2OKLAB.T


def delta_e_2000(lab1: np.ndarray, lab2: np.ndarray,
                 kL: float = 1.0, kC: float = 1.0, kH: float = 1.0) -> np.ndarray:
    """CIEDE2000（Sharma, Wu & Dalal 2005 实现笔记）。支持 numpy 广播。"""
    lab1 = np.asarray(lab1, dtype=np.float64)
    lab2 = np.asarray(lab2, dtype=np.float64)
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]

    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    Cbar7 = Cbar ** 7
    G = 0.5 * (1 - np.sqrt(Cbar7 / (Cbar7 + 25.0 ** 7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = np.hypot(a1p, b1)
    C2p = np.hypot(a2p, b2)

    def _hue(ap, b):
        h = np.degrees(np.arctan2(b, ap))
        h = np.where(h < 0, h + 360.0, h)
        return np.where((ap == 0) & (b == 0), 0.0, h)

    h1p = _hue(a1p, b1)
    h2p = _hue(a2p, b2)

    dLp = L2 - L1
    dCp = C2p - C1p
    prod_zero = (C1p * C2p) == 0
    dh = h2p - h1p
    dhp = np.where(prod_zero, 0.0,
          np.where(np.abs(dh) <= 180, dh,
          np.where(dh > 180, dh - 360.0, dh + 360.0)))
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2))

    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    hsum = h1p + h2p
    hbp = np.where(prod_zero, hsum,
          np.where(np.abs(h1p - h2p) <= 180, hsum / 2,
          np.where(hsum < 360, (hsum + 360.0) / 2, (hsum - 360.0) / 2)))

    T = (1 - 0.17 * np.cos(np.radians(hbp - 30))
           + 0.24 * np.cos(np.radians(2 * hbp))
           + 0.32 * np.cos(np.radians(3 * hbp + 6))
           - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dTheta = 30 * np.exp(-((hbp - 275) / 25) ** 2)
    Cbp7 = Cbp ** 7
    RC = 2 * np.sqrt(Cbp7 / (Cbp7 + 25.0 ** 7))
    SL = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    SC = 1 + 0.045 * Cbp
    SH = 1 + 0.015 * Cbp * T
    RT = -np.sin(np.radians(2 * dTheta)) * RC

    tL = dLp / (kL * SL)
    tC = dCp / (kC * SC)
    tH = dHp / (kH * SH)
    return np.sqrt(tL ** 2 + tC ** 2 + tH ** 2 + RT * tC * tH)


def pairwise_delta_e(lab_a: np.ndarray, lab_b: np.ndarray) -> np.ndarray:
    """(m,3) × (n,3) → (m,n) 的 ΔE2000 矩阵。"""
    return delta_e_2000(lab_a[:, None, :], lab_b[None, :, :])
