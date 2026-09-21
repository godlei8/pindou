"""平涂插画：每格取原图自己的一种颜色，而不是几种颜色的平均。

问题（2026-09-21，草莓样图）：原图描边 7px 宽、每格 8.3px——描边永远盖不满一格。
按面积平均后，描边上每一格都是"墨色 + 红色"按不同比例混出来的颜色，各自占掉一个色号：
描边三种深红交替、每颗籽由四种颜色拼成；而且没有一格是纯墨色，选色时根本选不到真正的墨色。

平涂插画本来就只有几种颜色，过渡色全是抗锯齿和缩小造成的。所以分三步：
1. **认墨**（detect_inks）：图是不是平涂的、有哪几种墨。照片、渐变插画认不出来，走原来的面积平均。
2. **标像素**（label_source）：每个像素是哪种墨；抗锯齿的混色像素归到它旁边实际有的颜色。
3. **取格**（downsample_inks）：初稿 + 直接按还原度逐格优化（core/refine.py）。
   这一步没有"最深的颜色是描边"之类的特殊规则：线要连续、轮廓要闭合、高光要留、眼睛别撑胖，
   都是"优化还原度 + 不许把同色区域断开"的自然结果，对什么颜色的线、什么样的小特征都一样。
"""
from __future__ import annotations

import numpy as np

from app.core.color import srgb_to_oklab
from app.core.downsample import CellImage

#: 一种颜色的"实心"像素（周围 8 格都是它自己）要有这么多才算一种墨。
#: 数实心像素而不是总像素：抗锯齿过渡色几乎不会自己连成实心的一片，
#: 所以门槛可以放得很低——小小的草莓籽、眼睛高光也能认出来。
MIN_INK_INTERIOR = 0.0001
MIN_INK_INTERIOR_PX = 12
#: 两种墨至少差这么多（OKLab）；更近的当作同一种墨的轻微变化
INK_SEPARATION = 0.05
#: 离某种墨这么近的像素算"就是这种墨"
INK_TOLERANCE = 0.04
#: 这么多像素都是某种墨，才算平涂插画
MIN_FLAT_SHARE = 0.9
MAX_INKS = 24
#: 该空的填了、该填的空了，按这么大的色差算（和 core/fidelity.py 一致）
SHAPE_PENALTY = 50.0
#: 认墨时把图缩到这么大（最近邻，不产生新颜色）：4000² 的照片没必要逐像素看
_DETECT_LONG_SIDE = 1024


#: 实心像素的"同色"允许差这么多（0–255）：画图软件导出的色块常有 ±2 的抖动
_SAME = 3
#: 第二遍补墨：既不是某种墨、也不是两种墨之间的抗锯齿混色（sRGB 里离混色线段超过这么远），
#: 同一个颜色却有这么多像素——那是一个真实的小色块，只是太窄认不出"实心"（小图里的嘴唇）。
#: 实测：真正的抗锯齿、锐化残留，单个颜色最多占 0.06%；1 像素一格的小图里嘴唇占 0.35%。
_BLEND_TOL = 0.06
MISSED_INK_SHARE = 0.002
MISSED_INK_PX = 4
#: 实心像素里不同颜色超过这么多种，肯定不是平涂（照片的平滑区域），提前放弃
_MAX_SOLID_COLORS = 4000


def _small_rgb8(rgba: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """缩到 _DETECT_LONG_SIDE 以内（隔点取样，不产生新颜色）。返回 0–255 的颜色和不透明掩码。"""
    h, w = rgba.shape[:2]
    step = max(1, int(np.ceil(max(h, w) / _DETECT_LONG_SIDE)))
    small = rgba[::step, ::step]
    q = np.clip(np.rint(small[..., :3] * 255), 0, 255).astype(np.int16)
    return q, small[..., 3] >= 0.5


#: 平涂的判据（2026-09-21 用多类型基准图重定）：
#: ① 实心像素的颜色高度集中：离各自那种墨不超过 CORE_TOL 的要占实心像素的 MIN_CORE_SHARE。
#:    渐变（苹果的高光、天空）的实心像素颜色是连续铺开的，过不了这一条——
#:    原来只要求"离某种墨 0.04 以内"，而墨与墨只隔 0.05，一条渐变会被几种墨完全"解释"，
#:    结果渐变苹果被当成平涂、拼出一圈圈色环。
#: ② 全部像素的 MIN_FLAT_SHARE 要能解释成"某种墨"或"两种墨之间的抗锯齿混色"。
#:    原来混色不算，线很细的线稿、128px 的小图抗锯齿像素占比高，被误判成照片。
#: ③ 第二遍补认的墨（太细没有实心像素的线、小色块）总量不能超过 MAX_MISSED_MASS——
#:    补墨是给小东西用的，大片都靠补墨才能解释的图不是平涂。
CORE_TOL = 0.03                  # sRGB 0–1，每通道约 ±5 级：放得下 JPEG 噪点，放不下渐变
#:    （0.06 不行：墨与墨隔 0.05 OKLab ≈ 0.1 sRGB，半径 0.06 的球正好把一条渐变铺满）
MIN_CORE_SHARE = 0.85
MIN_SOLID_SHARE = 0.05
MAX_MISSED_MASS = 0.25
#: 补认的墨：一团颜色里，挤在中心 _PEAK_TOL 以内的要占这么多（渐变是均匀铺开的，到不了）
_PEAK_TOL = 0.025
_OVERSHOOT = 0.25
MIN_PEAK = 0.6


def _rgb_of(keys: np.ndarray) -> np.ndarray:
    return np.stack([(keys >> 16) & 255, (keys >> 8) & 255, keys & 255], -1) / 255.0


def _unexplained(u: np.ndarray, inks: np.ndarray) -> np.ndarray:
    """每种颜色离"某种墨或两种墨的混色线段"有多远（sRGB 欧氏距离）。"""
    best = np.linalg.norm(u[:, None] - inks[None], axis=-1).min(1)
    for i in range(len(inks)):
        for j in range(i + 1, len(inks)):
            a, d = inks[i], inks[j] - inks[i]
            # 线段两头各多出 _OVERSHOOT：缩放（Lanczos 等）会在边缘产生过冲，
            # 比深色墨更深一点、比浅色墨更浅一点，仍然是这两种墨"混"出来的
            t = np.clip((u - a) @ d / max(float(d @ d), 1e-12), -_OVERSHOOT, 1 + _OVERSHOOT)
            best = np.minimum(best, np.linalg.norm(u - (a + t[:, None] * d), axis=1))
    return best


def detect_inks(rgba: np.ndarray) -> np.ndarray | None:
    """认出平涂插画的几种墨，返回 (k, 3) 的 sRGB（0–1）。不是平涂插画返回 None。"""
    q, opaque = _small_rgb8(rgba)
    n = int(opaque.sum())
    if n < 64:
        return None

    # 实心像素：周围 8 格都不透明、颜色都和自己几乎一样
    h, w = opaque.shape
    qp = np.pad(q, ((1, 1), (1, 1), (0, 0)), mode="edge")
    op = np.pad(opaque, 1, constant_values=False)
    interior = opaque.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                nb = qp[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
                interior &= op[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
                interior &= np.abs(nb - q).max(-1) <= _SAME
    n_solid = int(interior.sum())
    if n_solid < MIN_SOLID_SHARE * n:
        return None                                       # 几乎没有平整的色块：照片

    qi = q[interior].astype(np.int64)
    keys, counts = np.unique((qi[:, 0] << 16) | (qi[:, 1] << 8) | qi[:, 2], return_counts=True)
    if len(keys) > _MAX_SOLID_COLORS:
        return None
    rgb_keys = _rgb_of(keys)
    ok_keys = srgb_to_oklab(rgb_keys.astype(np.float64))

    # 从最常见的颜色开始认墨；和已认出的墨很近的（同一种墨的抖动）把票数并过去
    ink_idx: list[int] = []
    ink_votes: list[int] = []
    core = 0
    for i in np.argsort(-counts):
        if ink_idx:
            d = np.linalg.norm(ok_keys[ink_idx] - ok_keys[i], axis=1)
            j = int(d.argmin())
            if d[j] < INK_SEPARATION:
                ink_votes[j] += int(counts[i])
                if np.linalg.norm(rgb_keys[ink_idx[j]] - rgb_keys[i]) <= CORE_TOL:
                    core += int(counts[i])
                continue
        ink_idx.append(int(i))
        ink_votes.append(int(counts[i]))
        core += int(counts[i])
    if core < MIN_CORE_SHARE * n_solid:
        return None                                       # 实心像素的颜色是铺开的：渐变
    min_solid = max(MIN_INK_INTERIOR_PX, MIN_INK_INTERIOR * n)
    inks = [rgb_keys[i] for i, v in zip(ink_idx, ink_votes) if v >= min_solid]
    if not 1 <= len(inks) <= MAX_INKS:
        return None

    qa = q[opaque].astype(np.int64)
    akeys, acounts = np.unique((qa[:, 0] << 16) | (qa[:, 1] << 8) | qa[:, 2], return_counts=True)
    u = _rgb_of(akeys)
    # 去掉的背景色不是墨，但图形边缘的抗锯齿像素是"某种墨 + 背景色"混出来的，解释混色时要算上它
    extra = _background_color(q, opaque)
    inks, missed_mass = _add_missed_inks(u, acounts, inks, n, extra)
    if not 2 <= len(inks) <= MAX_INKS or missed_mass > MAX_MISSED_MASS * n:
        return None
    best = _unexplained(u, np.array(inks + extra))
    if acounts[best <= _BLEND_TOL].sum() < MIN_FLAT_SHARE * n:
        return None
    return np.array(inks, dtype=np.float32)


def _background_color(q: np.ndarray, opaque: np.ndarray) -> list:
    """透明区（去掉的背景）里最常见的颜色；透明区很小或没有就返回 []。"""
    t = q[~opaque].astype(np.int64)
    if len(t) < 0.02 * opaque.size:
        return []
    keys, counts = np.unique((t[:, 0] << 16) | (t[:, 1] << 8) | t[:, 2], return_counts=True)
    return [_rgb_of(keys[[int(counts.argmax())]])[0]]


def _prune_blends(inks: list, extra: list, base: int) -> list:
    kept = list(inks)
    for m in inks[base:]:
        others = [k for k in kept if k is not m] + extra
        if len(others) >= 2 and _unexplained(np.array([m]), np.array(others))[0] <= _BLEND_TOL:
            kept = [k for k in kept if k is not m]
    return kept


def _add_missed_inks(u: np.ndarray, counts: np.ndarray, inks: list, n: int,
                     extra: list | None = None) -> tuple[list, int]:
    """补认实心像素认不出来的墨：太细的线（2.5px 的线稿没有 3×3 的实心像素）、小图里的小色块。
    条件：不是已有的墨、也不是两种墨的混色；一团颜色够多（MISSED_INK_SHARE）而且挤在一个点上。"""
    inks, extra = list(inks), list(extra or [])
    base = len(inks)                                      # 前 base 个是实心像素认出来的，不动
    ok_u = srgb_to_oklab(u.astype(np.float64))
    alive = np.ones(len(u), dtype=bool)
    need = max(MISSED_INK_PX, MISSED_INK_SHARE * n)
    mass_added = 0
    for _ in range(3 * MAX_INKS):
        # 离已有的墨不到 INK_SEPARATION 的是同一种墨的变化（缩放时线边上的过冲会比墨色更深一点），
        # 不是新的墨——猫样图里它曾被认成"更深的一种墨"，把描边的逻辑整个带偏
        ok_inks = srgb_to_oklab(np.array(inks, dtype=np.float64))
        far = np.linalg.norm(ok_u[:, None] - ok_inks[None], axis=-1).min(1) >= INK_SEPARATION
        cand = alive & far & (_unexplained(u, np.array(inks + extra)) > _BLEND_TOL)
        if counts[cand].sum() < need or len(inks) > MAX_INKS:
            break
        idx = np.flatnonzero(cand)
        center = idx[int(counts[idx].argmax())]
        d = np.linalg.norm(u[idx] - u[center], axis=1)
        mass = int(counts[idx][d <= _BLEND_TOL].sum())
        peak = int(counts[idx][d <= _PEAK_TOL].sum())
        if mass >= need and peak >= MIN_PEAK * mass:
            inks.append(u[center])
            mass_added += mass
        else:
            alive[idx[d <= _PEAK_TOL]] = False            # 这一团不是墨，别再从它开始

    # 补认是从"像素最多的颜色"开始的，可能先认了一个混色（线稿里线和白底之间的灰），
    # 后来才认出线本身的颜色。回头清一遍：能被别的墨混出来的不是墨。
    return _prune_blends(inks, extra, base), mass_added


#: 取色时每格固定看这么多像素见方：大图缩小、小图平滑放大到同一个尺度，
#: 后面的投票、优化、还原度都在这个尺度上算
PX = 8
#: 混色像素在这么多像素之内找"旁边实际有的颜色"
_NEAR_PX = 3


def label_source(rgba: np.ndarray, rows: int, cols: int, inks: np.ndarray) -> np.ndarray:
    """把原图变成"墨标签图"：每格 PX×PX 像素，每个像素是 0..k-1 的某种墨，k = 透明/背景。"""
    import cv2
    h, w = rgba.shape[:2]
    tw, th = cols * PX, rows * PX
    a = rgba[..., 3:4].astype(np.float32)
    pre = np.concatenate([rgba[..., :3].astype(np.float32) * a, a], -1)   # 预乘，透明区颜色不渗进来
    interp = cv2.INTER_AREA if tw * th <= w * h else cv2.INTER_CUBIC
    pre = cv2.resize(pre, (tw, th), interpolation=interp)
    alpha = np.clip(pre[..., 3], 0, 1)
    rgb = np.clip(pre[..., :3] / np.maximum(alpha, 1e-6)[..., None], 0, 1)

    k = len(inks)
    ok = srgb_to_oklab(rgb.astype(np.float64))
    ok_inks = srgb_to_oklab(inks.astype(np.float64))
    d = np.linalg.norm(ok[..., None, :] - ok_inks[None, None], axis=-1)
    label = d.argmin(-1)
    transparent = alpha < 0.5
    solid = (d.min(-1) <= INK_TOLERANCE) & ~transparent

    # 抗锯齿的混色像素：只能归到它**旁边实际有的**那几种颜色里最像的一种（含背景）。
    # 全局挑最像的会出错——"深棕描边 + 橙色"的混色最像鼻子的玫红，整圈轮廓会冒出玫红的豆；
    # "浅蓝背景 + 深棕线"的混色最像眼睛的蓝。
    near = np.stack([ndimage_dilate(solid & (label == i), _NEAR_PX) for i in range(k)], -1)
    dm = np.where(near, d, np.inf)
    q8 = np.clip(np.rint(rgba[..., :3] * 255), 0, 255).astype(np.int16)
    bg = _background_color(q8, rgba[..., 3] >= 0.5)
    if bg and transparent.any():
        ok_bg = srgb_to_oklab(np.array(bg, dtype=np.float64))[0]
        d_bg = np.where(ndimage_dilate(transparent, _NEAR_PX), np.linalg.norm(ok - ok_bg, axis=-1), np.inf)
        dm = np.concatenate([dm, d_bg[..., None]], -1)       # 第 k 个候选 = 背景
        # 紧挨透明区、比任何墨都更像背景的像素就是没去干净的背景——哪怕它"够像"某种墨
        # （蘑菇的米色菌柄和浅绿背景很接近，描边外残留的背景像素会被当成米色，
        #  于是"米色挨着空白"在原图里成立，轮廓就不保证闭合了）
        solid &= ~(d_bg < d.min(-1))
    mixed = ~solid & ~transparent & np.isfinite(dm).any(-1)
    # 从后往前取最小：并列时选背景（文字和背景同色的 logo，边缘的光晕应该算背景不算文字）
    chosen = dm.shape[-1] - 1 - dm[mixed][:, ::-1].argmin(-1)
    # 例外：旁边的候选都差得远、而全局有一种墨几乎就是它——那是一条细到没有"实打实"像素的线
    # （2.5px 的花茎画在白底上，旁边只有背景可选，整条线会被归成背景）。差三倍以上才算"差得远"，
    # 不然上面说的"描边 + 橙 ≈ 玫红"又会回来。
    override = d[mixed].min(-1) < dm[mixed].min(-1) / 3.0
    label[mixed] = np.where(override, d[mixed].argmin(-1), chosen)
    label[transparent] = k
    return label


def ndimage_dilate(mask: np.ndarray, r: int) -> np.ndarray:
    from scipy import ndimage
    return ndimage.maximum_filter(mask.astype(np.uint8), size=2 * r + 1) > 0


def downsample_inks(rgba: np.ndarray, rows: int, cols: int, inks: np.ndarray,
                    coverage: np.ndarray | None = None) -> CellImage:
    """平涂取色：初稿"每格谁多用谁"，然后直接按还原度逐格优化（core/refine.py）。"""
    from app.core.color import delta_e_2000, srgb_to_lab
    from app.core.refine import Objective, refine, thin_first_init

    k = len(inks)
    src = label_source(rgba, rows, cols, inks)
    votes = (src.reshape(rows, PX, cols, PX)[..., None] == np.arange(k + 1)).sum((1, 3))
    if coverage is None:
        coverage = (1.0 - votes[..., k] / float(PX * PX)).astype(np.float32)
    init = thin_first_init(votes, src, k, PX)

    lab = srgb_to_lab(inks.astype(np.float64))
    cost = np.full((k + 1, k + 1), SHAPE_PENALTY)
    cost[:k, :k] = delta_e_2000(lab[:, None, :], lab[None, :, :])
    cost[k, k] = 0.0
    shared: dict = {}
    out = refine(Objective(src, k, cost, PX, shared), init)

    mask = out != k
    rgb = inks[np.where(mask, out, 0)].astype(np.float32)
    used = np.unique(out[mask])
    return CellImage(rgb=rgb, coverage=coverage, mask=mask, inks=inks[used],
                     flat_cache={"src": src, "k": k, "all_inks": inks, "shared": shared})
