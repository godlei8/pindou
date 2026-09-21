"""还原度：图纸拼出来像不像原图。

可拼性（buildability）只量"好不好拼"，完全不看像不像：猫样图轮廓断了 7 处、眼睛高光丢了，
可拼性照样 100；把高光补回来反而因为"零星小色"掉到 97。用户要的是还原度越高越好，
所以还原度单独算、单独显示，算法取舍以它为准。

两种图两种比法（2026-09-21 试出来的，数据见 spec「还原度」）：

**平涂插画按色块比**（measure 传了 inks）。原图每个像素归到它那种墨，然后双向检查：
原图的每一点，半格之内的图纸上有没有这种颜色的豆；图纸的每一点，半格之内的原图上有没有这种墨。
没有就按两种颜色的 ΔE2000 记误差（该空的填了、该填的空了按 SHAPE_PENALTY）。
半格的宽容是因为一格只能一个颜色，线画在左边一格还是右边一格不算错；
线断了、高光丢了、眼睛胖一圈、冒出原图没有的过渡色，都会被记下来。
不能用"模糊后逐点比颜色"：那种指标数学上偏爱取平均，会给"描边三种深红交替"打更高的分
（试过：草莓 87 对 80）。

**照片按远看比**（没有 inks）。原图和图纸都铺白底、模糊掉约一颗豆的细节，逐点比 ΔE2000。
照片本来就靠相近颜色的混合来表现，取平均是对的。

总误差 = 全图平均和"最差 5% 的平均"各占一半——只看平均的话，
一两格的小特征（眼睛高光、嘴）丢了会被大面积纯色淹没。
"""
from __future__ import annotations

import cv2
import numpy as np

from app.core.color import delta_e_2000, linear_to_srgb, srgb_to_lab, srgb_to_linear
from app.core.types import EMPTY

#: 每格看这么多像素见方
_PX_PER_CELL = 8
#: 模糊半径（高斯 σ），单位：格
BLUR_CELLS = 0.6
WORST_SHARE = 0.05
WORST_WEIGHT = 0.5
#: 还原度 = 100 - SLOPE × 总误差
SLOPE = 2.0


def _on_white_blurred(rgb: np.ndarray, alpha: np.ndarray, sigma: float) -> np.ndarray:
    lin = srgb_to_linear(rgb.astype(np.float32)) * alpha[..., None] + (1.0 - alpha[..., None])
    lin = cv2.GaussianBlur(lin.astype(np.float32), (0, 0), sigma)
    return srgb_to_lab(np.clip(linear_to_srgb(lin), 0, 1).astype(np.float64))


#: 平涂比法：该空的填了、该填的空了，按这么大的色差算
SHAPE_PENALTY = 50.0
#: 平涂比法：找对应颜色的宽容半径，单位：格
REACH_CELLS = 0.5


def _summary(e: np.ndarray, method: str) -> dict:
    mean = float(e.mean())
    n_worst = max(1, int(round(WORST_SHARE * e.size)))
    worst = float(np.partition(e, -n_worst)[-n_worst:].mean())
    overall = (1 - WORST_WEIGHT) * mean + WORST_WEIGHT * worst
    return {
        "score": round(float(np.clip(100.0 - SLOPE * overall, 0.0, 100.0)), 1),
        "mean_delta_e": round(mean, 2),
        "worst_delta_e": round(worst, 2),
        "method": method,
    }


def _measure_flat(src_rgb, src_a, big, palette_rgb, inks) -> dict:
    from app.core.color import srgb_to_oklab
    k = len(inks)
    ok = srgb_to_oklab(src_rgb.astype(np.float64))
    ok_inks = srgb_to_oklab(inks.astype(np.float64))
    src = np.linalg.norm(ok[..., None, :] - ok_inks[None, None], axis=-1).argmin(-1)
    src[src_a < 0.5] = k                                   # k = 透明
    colors = [int(c) for c in np.unique(big) if c != EMPTY]
    pat = np.full(big.shape, len(colors), dtype=np.int64)  # len(colors) = 空
    for j, c in enumerate(colors):
        pat[big == c] = j

    d = np.full((k + 1, len(colors) + 1), SHAPE_PENALTY)
    d[k, len(colors)] = 0.0
    if colors:
        d[:k, :len(colors)] = delta_e_2000(
            srgb_to_lab(inks.astype(np.float64))[:, None, :],
            srgb_to_lab(palette_rgb[colors] / 255.0)[None, :, :])

    r = max(1, int(round(REACH_CELLS * _PX_PER_CELL)))
    disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    near_pat = np.stack([cv2.dilate((pat == j).astype(np.uint8), disc) > 0
                         for j in range(len(colors) + 1)], -1)
    near_src = np.stack([cv2.dilate((src == i).astype(np.uint8), disc) > 0
                         for i in range(k + 1)], -1)
    e_src = np.where(near_pat, d[src], np.inf).min(-1)     # 原图这一点，附近的图纸上最像的豆
    e_pat = np.where(near_src, d.T[pat], np.inf).min(-1)   # 图纸这一点，附近的原图上最像的墨
    region = (src != k) | (pat != len(colors))
    return _summary(((e_src + e_pat) / 2)[region], "flat")


def measure(rgba: np.ndarray, grid: np.ndarray, palette_rgb: np.ndarray,
            inks: np.ndarray | None = None) -> dict | None:
    """rgba：出图时实际用的原图（已去背景），0–1 浮点。palette_rgb：0–255。
    inks：平涂插画认出来的几种墨（flat.detect_inks），照片传 None。全空时返回 None。"""
    rows, cols = grid.shape
    if not (grid != EMPTY).any():
        return None
    # 原图缩放到每格 _PX_PER_CELL 像素（预乘 alpha，免得透明区的颜色渗进来）
    w, h = cols * _PX_PER_CELL, rows * _PX_PER_CELL
    a = rgba[..., 3:4].astype(np.float32)
    pre = cv2.resize(np.concatenate([rgba[..., :3].astype(np.float32) * a, a], -1), (w, h),
                     interpolation=cv2.INTER_AREA)
    src_a = pre[..., 3]
    src_rgb = pre[..., :3] / np.maximum(src_a, 1e-6)[..., None]

    big = np.kron(grid, np.ones((_PX_PER_CELL, _PX_PER_CELL), dtype=grid.dtype))
    if inks is not None:
        return _measure_flat(src_rgb, src_a, big, palette_rgb, inks)
    pat_a = (big != EMPTY).astype(np.float32)
    pat_rgb = (palette_rgb[np.where(big == EMPTY, 0, big)] / 255.0).astype(np.float32)

    sigma = BLUR_CELLS * _PX_PER_CELL
    err = delta_e_2000(_on_white_blurred(src_rgb, src_a, sigma),
                       _on_white_blurred(pat_rgb, pat_a, sigma))
    region = cv2.GaussianBlur(np.maximum(src_a, pat_a), (0, 0), sigma) > 0.05
    return _summary(err[region], "blur")
