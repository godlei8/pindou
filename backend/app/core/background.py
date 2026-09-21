from __future__ import annotations

import numpy as np
from scipy import ndimage

from app.core.color import srgb_to_oklab

_CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])


def remove_background(rgba: np.ndarray, seed_xy: tuple[int, int], tolerance: float = 0.08) -> np.ndarray:
    x, y = int(seed_xy[0]), int(seed_xy[1])
    h, w = rgba.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        raise ValueError(f"seed {seed_xy} outside image {w}x{h}")
    ok = srgb_to_oklab(rgba[..., :3])
    within = np.linalg.norm(ok - ok[y, x], axis=-1) <= tolerance
    labels, _ = ndimage.label(within, structure=_CROSS)
    out = rgba.copy()
    out[labels == labels[y, x], 3] = 0.0
    return out


#: 边缘一圈至少这么大比例是同一个颜色，才认定是"纯色背景"。
#: 实测：纯色底的图（示例图、卡通、logo、贴纸）都是 100%；照片最高 66.8%（酒吧背景的人像），
#: 其余 24%–43%。取 90%，两边都留足余量——照片不会被误删背景。
BORDER_MIN_SHARE = 0.9
#: 检测和算掩码时先缩到这个尺寸：比网格细得多，边缘精度不受影响，4096px 大图也不慢
_WORK_LONG_SIDE = 1024


def remove_border_background(rgba: np.ndarray, tolerance: float = 0.08,
                             min_share: float = BORDER_MIN_SHARE) -> tuple[np.ndarray, bool]:
    """自动去掉纯色背景：边缘一圈几乎是同一个颜色时，把与边缘连通的那片同色区域设为透明。

    - **只去和边缘连通的部分**：蘑菇伞盖上的白点、小猫眼睛的高光和背景同色，
      但被主体包着、不和边缘连通，不会被误删。
    - 从边缘所有同色像素一起往里填，不是只从一个角：主体碰到画面边缘、
      把背景隔成左右两块时，两块都能去掉。
    - 边缘颜色不统一（照片）就什么都不做，返回 (原图, False)。
    """
    from PIL import Image

    h, w = rgba.shape[:2]
    # 先只看边缘一圈（直接从原图取、隔点抽样），判断是不是纯色底。
    # 照片是最常见的"不用去"情况，不能为它把整张大图先转换、缩小一遍（实测 4096px 白白多花 380ms）。
    step = max(1, max(h, w) // 512)
    ring = np.concatenate([rgba[0, ::step], rgba[-1, ::step], rgba[::step, 0], rgba[::step, -1]])
    ring = ring[ring[:, 3] > 0.5]
    if len(ring) < 8:                        # 边缘本来就几乎全透明，没什么可去的
        return rgba, False
    border = srgb_to_oklab(ring[:, :3])
    sub = border[:: max(1, len(border) // 400)]   # 400 个足够估出主色；两两比较是平方复杂度
    d = np.linalg.norm(sub[:, None] - sub[None], axis=-1)
    # 背景色 = 边缘上"同色邻居"最多的那个像素的颜色
    center = sub[int((d <= tolerance).sum(1).argmax())]
    share = float((np.linalg.norm(border - center, axis=-1) <= tolerance).mean())
    if share < min_share:
        return rgba, False

    # 确定是纯色底了，才去算整张图的掩码（在缩小的图上算，比网格细得多，边缘精度不受影响）
    s = min(1.0, _WORK_LONG_SIDE / max(h, w))
    if s < 1:
        small = np.asarray(Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8))
                           .resize((max(1, round(w * s)), max(1, round(h * s))), Image.BOX),
                           dtype=np.float32) / 255.0
    else:
        small = rgba
    sh, sw = small.shape[:2]
    ok = srgb_to_oklab(small[..., :3])
    opaque = small[..., 3] > 0.5
    frame = np.zeros((sh, sw), dtype=bool)
    frame[0, :] = frame[-1, :] = frame[:, 0] = frame[:, -1] = True

    within = (np.linalg.norm(ok - center, axis=-1) <= tolerance) & opaque
    labels, _ = ndimage.label(within, structure=_CROSS)
    edge_labels = np.unique(labels[frame & within])
    bg_small = np.isin(labels, edge_labels[edge_labels > 0])
    if not bg_small.any():
        return rgba, False

    if s < 1:
        bg = np.asarray(Image.fromarray(bg_small.astype(np.uint8) * 255)
                        .resize((w, h), Image.NEAREST)) > 127
    else:
        bg = bg_small
    out = rgba.copy()
    out[bg, 3] = 0.0
    return out, True
