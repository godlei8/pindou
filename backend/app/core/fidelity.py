"""还原度：图纸拼出来像不像原图。

可拼性（buildability）只量"好不好拼"，完全不看像不像：猫样图轮廓断了 7 处、眼睛高光丢了，
可拼性照样 100；把高光补回来反而因为"零星小色"掉到 97。用户要的是还原度越高越好，
所以还原度单独算、单独显示，算法取舍以它为准。

两种图两种比法（2026-09-21 试出来的，数据见 spec「还原度」）：

**平涂插画按色块比**（measure 传了 inks）。误差的定义在 core/refine.py 的 Objective 里，
取色时优化的就是它——打分的和优化的是同一个东西：
  · 原图的每一点：它那种颜色的豆最好就在自己这格；要靠邻格来"代为解释"，加一点代价（SLOP）；
    半格之内都没有，按两种颜色的 ΔE2000 记（线断了、高光丢了）。
  · 图纸的每一点：原图里这种颜色离得越远罚得越多；一格之内只是"线粗了一点"，轻罚；
    一格之外才有，重罚（冒出了原图那里没有的颜色）。
  · 原图的东西图纸上没有，比图纸上多出东西更伤还原度（0.65 : 0.35）。
走过的弯路：① "半格之内有这种颜色就算对"——隔一格放一颗的虚线、中间掏空的线都算全对，
优化器会忠实地钻这个空子；② "模糊后逐点比颜色"——数学上偏爱取平均，
会给"描边三种深红交替"打更高的分（试过：草莓 87 对 80）。

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


def _measure_flat(rgba, grid, palette_rgb, inks) -> dict:
    """平涂比法：误差的定义在 core/refine.py 的 Objective 里，和取色时优化的是同一个。"""
    from app.core.flat import PX, label_source
    from app.core.refine import Objective
    rows, cols = grid.shape
    k = len(inks)
    src = label_source(rgba, rows, cols, inks)
    colors = [int(c) for c in np.unique(grid) if c != EMPTY]
    pat = np.full(grid.shape, len(colors), dtype=np.int64)
    for j, c in enumerate(colors):
        pat[grid == c] = j
    cost = np.full((k + 1, len(colors) + 1), SHAPE_PENALTY)
    cost[k, len(colors)] = 0.0
    cost[:k, :len(colors)] = delta_e_2000(
        srgb_to_lab(inks.astype(np.float64))[:, None, :],
        srgb_to_lab(palette_rgb[colors] / 255.0)[None, :, :])
    e = Objective(src, k, cost, PX).error_map(pat)
    region = (src != k).reshape(2 * rows, PX // 2, 2 * cols, PX // 2).any((1, 3))         | np.repeat(np.repeat(pat != len(colors), 2, 0), 2, 1)
    return _summary(e[region], "flat")


def measure(rgba: np.ndarray, grid: np.ndarray, palette_rgb: np.ndarray,
            inks: np.ndarray | None = None) -> dict | None:
    """rgba：出图时实际用的原图（已去背景），0–1 浮点。palette_rgb：0–255。
    inks：平涂插画认出来的几种墨（flat.detect_inks），照片传 None。全空时返回 None。"""
    rows, cols = grid.shape
    if not (grid != EMPTY).any():
        return None
    if inks is not None:
        return _measure_flat(rgba, grid, palette_rgb, inks)
    # 原图缩放到每格 _PX_PER_CELL 像素（预乘 alpha，免得透明区的颜色渗进来）
    w, h = cols * _PX_PER_CELL, rows * _PX_PER_CELL
    a = rgba[..., 3:4].astype(np.float32)
    pre = cv2.resize(np.concatenate([rgba[..., :3].astype(np.float32) * a, a], -1), (w, h),
                     interpolation=cv2.INTER_AREA)
    src_a = pre[..., 3]
    src_rgb = pre[..., :3] / np.maximum(src_a, 1e-6)[..., None]

    big = np.kron(grid, np.ones((_PX_PER_CELL, _PX_PER_CELL), dtype=grid.dtype))
    pat_a = (big != EMPTY).astype(np.float32)
    pat_rgb = (palette_rgb[np.where(big == EMPTY, 0, big)] / 255.0).astype(np.float32)

    sigma = BLUR_CELLS * _PX_PER_CELL
    err = delta_e_2000(_on_white_blurred(src_rgb, src_a, sigma),
                       _on_white_blurred(pat_rgb, pat_a, sigma))
    region = cv2.GaussianBlur(np.maximum(src_a, pat_a), (0, 0), sigma) > 0.05
    return _summary(err[region], "blur")
