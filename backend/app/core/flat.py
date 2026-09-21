"""平涂插画：每格取原图自己的一种颜色，而不是几种颜色的平均。

问题（2026-09-21，草莓样图）：原图描边 7px 宽、每格 8.3px——描边永远盖不满一格。
按面积平均后，描边上每一格都是"墨色 + 红色"按不同比例混出来的颜色：
51% 墨是 F6、71% 墨是 R22、墨 + 绿是 B12；草莓籽（黄）和红混成 G6/A14/P16。
这些过渡色各自占掉一个色号，在图纸上表现为描边三种深红交替、每颗籽由四种颜色拼成。
更糟的是没有一格是纯墨色，选色时根本选不到真正的墨色（H16），
锁描边只好锁到"现有颜色里最深的"R13（一个灰色）。

平涂插画本来就只有几种颜色，过渡色全是抗锯齿和缩小造成的。所以：
先认出原图的几种"墨"，每格数一数哪种墨占得最多，就用那种墨的颜色。
照片颜色是连续的，认不出几种墨，自动走原来的面积平均。
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
#: 描边（最深的那种墨）按"先多收、再削薄"取格（见 _line_cells）：
#: 占一格面积 LINE_WEAK 以上的都先算候选；候选连成的一片里至少有一格占到 LINE_SHARE 才留
#: （滤掉零星的深色噪点）；然后把不过半、去掉也不会让线断开的格子按占比从小到大削掉。
#: 结果：线是连续的一颗宽，闭合的轮廓一定闭合；眼睛这类实心深色块不会被撑胖。
#:
#: 之前的做法是"占三成就算描边"：线正好骑在两格中间、两边各两成时两格都不算，
#: 轮廓就断了，去掉背景后填充色直接挨着空白（猫样图 58 格：7 处）。
LINE_SHARE = 0.3
LINE_WEAK = 0.1
#: 只有真的是"深色线"才这样照顾（OKLab 亮度）；没有描边的浅色插画不受影响
LINE_MAX_L = 0.45
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


def detect_inks(rgba: np.ndarray) -> np.ndarray | None:
    """认出平涂插画的几种墨，返回 (k, 3) 的 sRGB（0–1）。不是平涂插画返回 None。

    JPEG 压得很重的插画（色块里满是噪点）可能认不出来，会走原来的面积平均——
    结果和改动前一样，不会更差。"""
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

    qi = q[interior].astype(np.int64)
    keys, counts = np.unique((qi[:, 0] << 16) | (qi[:, 1] << 8) | qi[:, 2], return_counts=True)
    if len(keys) > _MAX_SOLID_COLORS:
        return None
    rgb_keys = np.stack([(keys >> 16) & 255, (keys >> 8) & 255, keys & 255], -1) / 255.0
    ok_keys = srgb_to_oklab(rgb_keys.astype(np.float64))

    # 从最常见的颜色开始认墨；和已认出的墨很近的（同一种墨的抖动）把票数并过去
    ink_idx: list[int] = []
    ink_votes: list[int] = []
    for i in np.argsort(-counts):
        if ink_idx:
            d = np.linalg.norm(ok_keys[ink_idx] - ok_keys[i], axis=1)
            j = int(d.argmin())
            if d[j] < INK_SEPARATION:
                ink_votes[j] += int(counts[i])
                continue
        ink_idx.append(int(i))
        ink_votes.append(int(counts[i]))
    min_solid = max(MIN_INK_INTERIOR_PX, MIN_INK_INTERIOR * n)
    inks = [i for i, v in zip(ink_idx, ink_votes) if v >= min_solid]
    if not 2 <= len(inks) <= MAX_INKS:
        return None

    # 多少像素"就是某种墨"：抗锯齿过渡色不算。按不同颜色算，比逐像素快一个量级
    qa = q[opaque].astype(np.int64)
    akeys, acounts = np.unique((qa[:, 0] << 16) | (qa[:, 1] << 8) | qa[:, 2], return_counts=True)
    ok_all = srgb_to_oklab(np.stack([(akeys >> 16) & 255, (akeys >> 8) & 255, akeys & 255],
                                    -1).astype(np.float64) / 255.0)
    dist = np.full(len(akeys), np.inf)
    for i in inks:
        dist = np.minimum(dist, np.linalg.norm(ok_all - ok_keys[i], axis=1))
    if acounts[dist <= INK_TOLERANCE].sum() / n < MIN_FLAT_SHARE:
        return None

    ink_rgb = [rgb_keys[i] for i in inks]
    ink_rgb += _missed_inks(akeys[dist > INK_TOLERANCE], acounts[dist > INK_TOLERANCE],
                            np.array(ink_rgb), n)
    if len(ink_rgb) > MAX_INKS:
        return None
    return np.array(ink_rgb, dtype=np.float32)


def _missed_inks(keys: np.ndarray, counts: np.ndarray, inks: np.ndarray, n: int) -> list:
    """实心像素认不出来的小色块（见 _BLEND_TOL 的说明）。"""
    if len(keys) == 0:
        return []
    u = np.stack([(keys >> 16) & 255, (keys >> 8) & 255, keys & 255], -1) / 255.0
    best = np.linalg.norm(u[:, None] - inks[None], axis=-1).min(1)
    for i in range(len(inks)):
        for j in range(i + 1, len(inks)):
            a, d = inks[i], inks[j] - inks[i]
            t = np.clip((u - a) @ d / max(d @ d, 1e-12), 0, 1)
            best = np.minimum(best, np.linalg.norm(u - (a + t[:, None] * d), axis=1))
    found: list[np.ndarray] = []
    for i in np.argsort(-counts):
        if counts[i] < max(MISSED_INK_PX, MISSED_INK_SHARE * n):
            break
        if best[i] <= _BLEND_TOL:
            continue
        if found and np.min(np.linalg.norm(np.array(found) - u[i], axis=1)) <= _BLEND_TOL:
            continue
        found.append(u[i])
    return found


#: 原图里一块某种墨的色块，面积有这么多格就不该在图纸上消失（草莓籽、眼睛高光）
MIN_FEATURE_CELLS = 0.4
#: 只照顾小色块：大色块自然有它的格子
MAX_FEATURE_CELLS = 2.0
#: 取色时每格最多看这么多像素见方：更大的图先缩小，省内存也省时间
_PX_PER_CELL = 12


def _c8(nb: np.ndarray) -> int:
    """3×3 邻域（中心不算）的 8-连通数（Yokoi）：1 = 去掉中心不改变连通性；
    0 = 内部点或孤立点；≥2 = 去掉会把线断开。"""
    x = [nb[1, 2], nb[0, 2], nb[0, 1], nb[0, 0], nb[1, 0], nb[2, 0], nb[2, 1], nb[2, 2]]
    inv = [1 - int(v) for v in x]
    return sum(inv[k] - inv[k] * inv[(k + 1) % 8] * inv[(k + 2) % 8] for k in (0, 2, 4, 6))


def _line_cells(share: np.ndarray) -> np.ndarray:
    """share: (rows, cols) 每格里描边墨占整格面积的比例。返回哪些格子算描边。"""
    from scipy import ndimage
    cand = share >= LINE_WEAK
    comp, n = ndimage.label(cand, structure=np.ones((3, 3), int))
    if n == 0:
        return cand
    peak = ndimage.maximum(share, comp, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, dtype=bool)
    keep[1:] = peak >= LINE_SHARE - 1e-9
    line = keep[comp]

    rows, cols = share.shape
    padded = np.pad(line, 1)
    weak = np.argwhere(line & (share < 0.5))
    for r, c in weak[np.argsort(share[weak[:, 0], weak[:, 1]], kind="stable")]:
        nb = padded[r:r + 3, c:c + 3]
        # 线头（只有一个邻居）不削：不然细线会从头被一格一格吃光
        if nb.sum() - 1 >= 2 and _c8(nb) == 1:
            padded[r + 1, c + 1] = False
    return padded[1:-1, 1:-1]


def downsample_inks(rgba: np.ndarray, rows: int, cols: int, inks: np.ndarray,
                    coverage: np.ndarray) -> CellImage:
    """每格取占像素最多的那种墨；深色描边单独取格（_line_cells）；小色块至少留一格。
    coverage 沿用面积平均算出来的。"""
    import cv2
    from scipy import ndimage

    h, w = rgba.shape[:2]
    limit = _PX_PER_CELL * max(rows, cols)
    if max(h, w) > limit:
        s = limit / max(h, w)
        rgba = cv2.resize(rgba, (max(cols, round(w * s)), max(rows, round(h * s))),
                          interpolation=cv2.INTER_AREA)
        h, w = rgba.shape[:2]
    ok = srgb_to_oklab(rgba[..., :3].astype(np.float64))
    ok_inks = srgb_to_oklab(inks.astype(np.float64))
    # 每个像素归到最近的墨：抗锯齿过渡色归到它更像的那一边
    label = np.empty((h, w), dtype=np.int16)
    solid = np.empty((h, w), dtype=bool)                # 颜色确实就是那种墨，不是抗锯齿过渡色
    for y0 in range(0, h, 128):
        d = np.linalg.norm(ok[y0:y0 + 128][..., None, :] - ok_inks[None, None], axis=-1)
        label[y0:y0 + 128] = d.argmin(-1)
        solid[y0:y0 + 128] = d.min(-1) <= INK_TOLERANCE
    label[rgba[..., 3] < 0.5] = -1                      # 去掉的背景不参与投票

    ys = np.minimum((np.arange(h) * rows) // h, rows - 1)
    xs = np.minimum((np.arange(w) * cols) // w, cols - 1)
    cell = ys[:, None] * cols + xs[None, :]
    k = len(inks)
    votes = np.zeros((rows * cols, k + 1), dtype=np.int64)
    np.add.at(votes, (cell.ravel(), label.ravel() + 1), 1)
    transparent, counts = votes[:, 0], votes[:, 1:].copy()
    area = np.maximum(votes.sum(1), 1)

    darkest = int(np.argmin(ok_inks[:, 0]))
    line = np.zeros(rows * cols, dtype=bool)
    if ok_inks[darkest, 0] < LINE_MAX_L:
        line = _line_cells((counts[:, darkest] / area).reshape(rows, cols)).ravel()
        counts[:, darkest] = 0                          # 其余格子在剩下的墨里比多少
    winner = counts.argmax(1)
    # 填豆还是留空：描边一定填；其余看"颜色"和"透明"谁多。没有描边墨的格子，这就是覆盖率过半
    mask = line | ((counts.sum(1) > 0) & (counts.sum(1) >= transparent))
    winner[line] = darkest

    # 小色块跨在几格的交界上，每格都不过半，按"谁多用谁"会整块消失（草莓籽、眼睛高光）。
    # 面积够大的色块如果一格都没分到，就把它占得最多的那格给它。
    # 描边的格子一般不抢——除非它在实心深色块里面、去掉不会让线断开（眼睛里的高光就是这样）。
    cell_px = h * w / (rows * cols)
    line2d = np.pad(line.reshape(rows, cols), 1)
    for ink in range(k):
        if ink == darkest and line.any():
            continue
        # 只认实打实是这种墨的像素：去背景后描边外面残留的一圈抗锯齿光晕会被归到某种浅色墨，
        # 它又细又长、面积正好像个"小色块"，会在轮廓外面凭空多出一颗豆（蘑菇样图 80 格）
        comp, n = ndimage.label((label == ink) & solid)
        if n == 0:
            continue
        sizes = np.bincount(comp.ravel())
        for cid, sl in enumerate(ndimage.find_objects(comp), start=1):
            if sl is None or not (MIN_FEATURE_CELLS * cell_px <= sizes[cid]
                                  <= MAX_FEATURE_CELLS * cell_px):
                continue
            cells = cell[sl][comp[sl] == cid]
            ids, c = np.unique(cells, return_counts=True)
            if (mask[ids] & (winner[ids] == ink)).any():
                continue
            for i in ids[np.argsort(-c, kind="stable")]:
                r, cc = divmod(int(i), cols)
                nb = line2d[r:r + 3, cc:cc + 3]
                if line[i] and (nb.sum() - 1 < 2 or _c8(nb) > 1):
                    continue                            # 细线的一环、线头、孤立的深色点：不能抢
                winner[i], mask[i], line[i] = ink, True, False
                line2d[r + 1, cc + 1] = False
                break

    # 保险：填充色上下左右直接挨着空白、而原图那里其实有描边——两格里描边多的那格补成描边
    if line.any():
        share = votes[:, 1 + darkest] / area
        m2, l2, s2 = mask.reshape(rows, cols), line.reshape(rows, cols), share.reshape(rows, cols)
        w2 = winner.reshape(rows, cols)
        for dr, dc in ((0, 1), (1, 0)):
            a = (slice(0, rows - dr), slice(0, cols - dc))
            b = (slice(dr, rows), slice(dc, cols))
            for fill, empty in ((a, b), (b, a)):
                bad = m2[fill] & ~l2[fill] & ~m2[empty] & (np.maximum(s2[fill], s2[empty]) >= 0.03)
                if not bad.any():
                    continue
                use_fill = s2[fill] >= s2[empty]
                for side, pick in ((fill, bad & use_fill), (empty, bad & ~use_fill)):
                    m2[side][pick] = True
                    l2[side][pick] = True
                    w2[side][pick] = darkest

    rgb = inks[winner].reshape(rows, cols, 3).astype(np.float32)
    return CellImage(rgb=rgb, coverage=coverage, mask=mask.reshape(rows, cols),
                     inks=inks[np.unique(winner[mask])])
