"""平涂图的通用优化：直接拿还原度当目标，逐格换颜色，变好就接受。

为什么：之前是"看到一个毛病补一条规则"——描边占三成算描边、骑缝的线削薄、高光抢一格、
光晕不算特征……而且都只认"最深的那种墨是描边"，换成彩色描边、深底浅线就不灵。
还原度指标（core/fidelity.py 的平涂比法）本身已经说清了什么叫"像"：
  · 原图的每一点，半格之内的图纸上要有这种颜色（线不能断、高光不能丢）；
  · 图纸的每一点，半格之内的原图上要有这种颜色（线不能平白变粗、不能冒出原图没有的颜色）。
那就直接优化它，任何颜色的线、任何小特征都一视同仁。

做法（坐标下降）：初稿对"细的东西"宁多勿少（见 thin_first_init）；然后对每个不是纯色的格子，
试着换成附近出现过的另一种墨（或留空），总误差下降就换；扫几遍直到不再变。最后一遍照顾可拼性：
孤零零的一颗豆试着并进邻居，**只有总误差不上升才并**——还原度第一，可拼性在它之后。

两条拓扑约束（对所有颜色一视同仁，没有"哪种颜色是描边"的概念）：
① 原图里从不相邻的两种颜色，图纸上也不许上下左右直接相邻。橙色填充和透明背景之间永远隔着描边，
   那图纸上橙色就不能直接挨着空白——这就是"轮廓要包住"。优化结束后还有残留的，用隔在中间的那种墨补上。
② **拿掉一颗豆如果会把同色的区域断成两截，就不许拿**（8-连通数 ≥ 2）。
没有它，优化会把线拼成虚线——"半格之内有这种颜色"隔一格放一颗也满足，还省了"线变粗"的代价。
人眼看重结构：线要连续、轮廓要闭合。有了它，初稿里连着的线只会被削薄，不会被削断；
两颗宽的线削成一颗、胖了一圈的眼睛削回原样，都是"去掉也不断开 + 误差下降"的自然结果。

为了能逐格快速算"换了以后误差变多少"，把每格切成 2×2 四个小块，每个小块能"够到"的格子固定是
自己那格 + 靠近的横向、纵向、斜向邻格（这就是"半格之内"）。
误差的定义在 Objective 里，评分（fidelity.measure）直接用它——优化的和打分的是同一个东西。
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

#: 原图的东西图纸上没有（线断了、高光丢了）比图纸上多出东西（线变粗）更伤还原度。
W_SRC, W_PAT = 0.65, 0.35
#: 位置上的宽容是有代价的：颜色就在自己这格最好；要靠邻格来"代为解释"，加 SLOP。
#: 没有它，"半格之内有这种颜色就算对"有两个漏洞：隔一格放一颗的虚线、中间掏空两边留着的线，都算全对。
SLOP = 12.0
#: 图纸上的颜色在原图一格之外才有：严重误差（冒出不该有的颜色）。一格之内：只是线粗了一点，按距离轻罚。
FAR = 50.0
MAX_SWEEPS = 8
#: 两种墨在原图里"相邻"：相邻的像素对至少有 MIN_TOUCH_CELLS 格边长那么多，
#: 或者占到其中较小那种墨全部边界的 MIN_TOUCH_SHARE（眼睛高光整个周长才几十像素，不能用固定门槛）。
#: 草莓籽和背景只有 16 对像素挨着（籽压在描边上），占籽边界的 2%：不算相邻。
MIN_TOUCH_CELLS = 3.0
MIN_TOUCH_SHARE = 0.15


class Objective:
    """还原度的误差。优化（refine）和评分（fidelity.measure）用的是同一个。

    src：原图的墨标签图，每格 px×px 像素，取值 0..k（k = 透明）。
    cost[i, j]：原图是墨 i、图纸上放的是第 j 种豆的色差；最后一行/列是透明/留空。
    """

    def __init__(self, src: np.ndarray, k: int, cost: np.ndarray, px: int):
        self.src, self.k, self.cost, self.px = src, k, cost, px
        self.rows, self.cols = src.shape[0] // px, src.shape[1] // px
        self.m = cost.shape[1] - 1                       # 图纸标签 0..m，m = 留空
        self.hist = self._quadrant_hist()
        self.ep_px = self._pattern_side()                # (h, w, m+1) 每个像素放 j 的误差
        self.ep = self.ep_px.reshape(self.rows, px, self.cols, px, -1).sum((1, 3))
        # 以格 (r, c) 为中心，受它影响的 4×4 个小块，以及每个小块够得到的四个格子（第一个是自己那格）
        qr, qc = np.meshgrid(np.arange(-1, 3), np.arange(-1, 3), indexing="ij")
        dr, dc = np.where(qr % 2 == 0, -1, 1), np.where(qc % 2 == 0, -1, 1)
        own_r, own_c = qr // 2, qc // 2
        self._qr, self._qc = qr, qc
        self._cell_r = np.stack([own_r, own_r + dr, own_r, own_r + dr], -1)
        self._cell_c = np.stack([own_c, own_c, own_c + dc, own_c + dc], -1)
        self._slop = np.array([0.0, SLOP, SLOP, SLOP])

    def _quadrant_hist(self) -> np.ndarray:
        half = self.px // 2
        onehot = (self.src[..., None] == np.arange(self.k + 1)).astype(np.float64)
        h = onehot.reshape(2 * self.rows, half, 2 * self.cols, half, self.k + 1).sum((1, 3))
        return np.pad(h, ((2, 2), (2, 2), (0, 0)))       # 四周垫一格（两个小块）

    def _pattern_side(self) -> np.ndarray:
        reach = self.px / 2
        dist = np.stack([ndimage.distance_transform_edt(self.src != i) if (self.src == i).any()
                         else np.full(self.src.shape, np.inf) for i in range(self.k + 1)], -1)
        place = SLOP * np.minimum(dist, 2 * reach) / reach + np.where(dist > 2 * reach, FAR, 0.0)
        out = np.empty((*self.src.shape, self.m + 1), dtype=np.float32)
        for j in range(self.m + 1):
            out[..., j] = (place + self.cost[:, j]).min(-1)
        return out

    def touching(self) -> np.ndarray:
        """A[i, j]：墨 i 和墨 j（含透明）在原图里是不是挨着。
        "挨着"放宽到隔两个像素：两种颜色交界处的抗锯齿像素可能被标成第三种墨
        （白色高光和深色眼线之间的混色被标成了头发的棕色），严格按相邻像素数会漏掉真实的相邻关系，
        结果高光哪儿都不许放。描边有好几个像素宽，隔两个像素够不着，填充色和背景仍然"不挨着"。"""
        k, s = self.k, self.src
        masks = [s == i for i in range(k + 1)]
        counts = np.zeros((k + 1, k + 1))
        for i in range(k + 1):
            if masks[i].any():
                near = ndimage.maximum_filter(masks[i].astype(np.uint8), size=5) > 0
                for j in range(k + 1):
                    if j != i:
                        counts[i, j] = (near & masks[j]).sum()
        counts = np.maximum(counts, counts.T)
        border = counts.sum(1)
        need = np.minimum(MIN_TOUCH_CELLS * self.px,
                          MIN_TOUCH_SHARE * np.minimum(border[:, None], border[None, :]))
        touch = (counts >= need) & (counts > 0)
        np.fill_diagonal(touch, True)
        return touch

    def source_window(self, pat: np.ndarray, r: int, c: int) -> float:
        """pat 四周垫过一格；(r, c) 是垫过的坐标。返回受这格影响的那 16 个小块的原图侧误差。"""
        labels = pat[r + self._cell_r, c + self._cell_c]                 # (4, 4, 4)
        best = (self.cost[:, labels] + self._slop).min(-1)               # (k+1, 4, 4)
        h = self.hist[2 * r + self._qr, 2 * c + self._qc]                # (4, 4, k+1)
        return float((h * np.moveaxis(best, 0, -1)).sum())

    def error_map(self, pat: np.ndarray) -> np.ndarray:
        """每个小块的平均误差，(2·rows, 2·cols)。pat：(rows, cols)，取值 0..m。"""
        p = np.pad(pat, 1, constant_values=self.m)
        rows, cols, half = self.rows, self.cols, self.px // 2
        src_side = np.zeros((2 * rows, 2 * cols))
        for a in (0, 1):
            for b in (0, 1):
                dr, dc = (-1 if a == 0 else 1), (-1 if b == 0 else 1)
                own = p[1:-1, 1:-1]
                cells = [own, p[1 + dr:rows + 1 + dr, 1:-1], p[1:-1, 1 + dc:cols + 1 + dc],
                         p[1 + dr:rows + 1 + dr, 1 + dc:cols + 1 + dc]]
                best = np.stack([self.cost[:, lab] + s for lab, s in zip(cells, self._slop)], 0).min(0)
                h = self.hist[2 + a:2 + 2 * rows:2, 2 + b:2 + 2 * cols:2]        # (rows, cols, k+1)
                src_side[a::2, b::2] = (h * np.moveaxis(best, 0, -1)).sum(-1)
        big = np.repeat(np.repeat(pat, self.px, 0), self.px, 1)
        pat_px = np.take_along_axis(self.ep_px, big[..., None], -1)[..., 0]
        pat_side = pat_px.reshape(2 * rows, half, 2 * cols, half).sum((1, 3))
        return (W_SRC * src_side + W_PAT * pat_side) / float(half * half)


def c8(nb: np.ndarray) -> int:
    """3×3 邻域（中心不算）的 8-连通数（Yokoi）：1 = 去掉中心不改变连通性；
    0 = 内部点或孤立点；≥2 = 去掉会把区域断开。"""
    x = [nb[1, 2], nb[0, 2], nb[0, 1], nb[0, 0], nb[1, 0], nb[2, 0], nb[2, 1], nb[2, 2]]
    inv = [1 - int(v) for v in x]
    return sum(inv[i] - inv[i] * inv[(i + 1) % 8] * inv[(i + 2) % 8] for i in (0, 2, 4, 6))


def thin_first_init(votes: np.ndarray, src: np.ndarray, k: int, px: int,
                    boost: float = 8.0) -> np.ndarray:
    """初稿：每格取"加权后"像素最多的墨。越细的墨权重越高——细线每格只占一两成，
    按"谁多用谁"一格都拿不到，而优化只会一格一格地加，容易加成虚线；
    先让细的东西多占，连成线，再由优化（带拓扑约束）削薄，线就不会断。
    细不细 = 这种墨的像素里，离边界不到半格的占多少。"""
    rows, cols = votes.shape[:2]
    share = votes / float(px * px)
    weight = np.ones(k + 1)
    for i in range(k):
        m = src == i
        area = int(m.sum())
        if area:
            core = ndimage.binary_erosion(m, iterations=max(1, px // 2)).sum()
            weight[i] = 1.0 + boost * (1.0 - core / area)
    return (share * weight).argmax(-1)


def refine(obj: Objective, init: np.ndarray) -> np.ndarray:
    """init：初稿（每格一个标签，0..m，m = 留空；这里图纸标签和墨一一对应，m = k）。返回优化后的标签。"""
    k, rows, cols = obj.m, obj.rows, obj.cols
    pat = np.pad(init.astype(np.int64), 1, constant_values=k)

    # 每格的候选：周围 3×3 格的原图里出现过的墨（含透明 = 留空）
    cell_has = obj.hist[2:-2, 2:-2].reshape(rows, 2, cols, 2, -1).sum((1, 3)) > 0
    present = ndimage.maximum_filter(cell_has.astype(np.uint8), size=(3, 3, 1)) > 0
    active = np.argwhere(present.sum(-1) >= 2)

    touch = obj.touching()

    def allowed(r: int, c: int, new: int) -> bool:
        """图外面不算邻居：贴着图片边缘的颜色不是"挨着空白"。"""
        return all(touch[new, int(pat[rr + 1, cc + 1])]
                   for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
                   if 0 <= rr < rows and 0 <= cc < cols)

    def delta(r: int, c: int, new: int) -> float:
        cur = int(pat[r + 1, c + 1])
        before = obj.source_window(pat, r + 1, c + 1)
        pat[r + 1, c + 1] = new
        after = obj.source_window(pat, r + 1, c + 1)
        pat[r + 1, c + 1] = cur
        return W_SRC * (after - before) + W_PAT * (obj.ep[r, c, new] - obj.ep[r, c, cur])

    def breaks(r: int, c: int, cur: int) -> bool:
        """把这格换掉，会不会把同色的区域断开。线头不用特别保护：线头那格里的墨离前一格够远，
        拿掉它误差是上升的，优化自己就不会拿；硬性保护反而会在削薄两格宽的线时留下一颗颗小尾巴。"""
        if cur == k:
            return False
        nb = pat[r:r + 3, c:c + 3] == cur
        return int(nb.sum()) - 1 >= 2 and c8(nb) >= 2

    def best_move(r: int, c: int) -> tuple[float, int]:
        cur = int(pat[r + 1, c + 1])
        best, best_d = cur, -1e-6
        if not breaks(r, c, cur):
            for j in np.flatnonzero(present[r, c]):
                if j != cur and allowed(r, c, int(j)):
                    d = delta(r, c, int(j))
                    if d < best_d:
                        best, best_d = int(j), d
        return best_d, best

    # 每一轮：先算出所有格子各自最好的改动，再按收益从大到小执行（执行前按当时的状态重算一次）。
    # 按从上到下的顺序边算边改会陷进局部最优：两格宽的初稿线，先碰到的那格被换成了旁边的填充色，
    # 而真正该换的是另一格（收益大得多）——猫样图轮廓外因此多出几颗孤零零的橙豆。
    for _ in range(MAX_SWEEPS):
        moves = []
        for r, c in active:
            d, j = best_move(r, c)
            if j != pat[r + 1, c + 1]:
                moves.append((d, int(r), int(c)))
        changed = 0
        for _, r, c in sorted(moves):
            d, j = best_move(r, c)
            if j != pat[r + 1, c + 1]:
                pat[r + 1, c + 1] = j
                changed += 1
        if not changed:
            break

    # 可拼性：孤零零的一颗豆（上下左右没有同色的）试着并进邻居——只有还原度不受损才并
    for r, c in active:
        cur = int(pat[r + 1, c + 1])
        nb = [int(pat[r, c + 1]), int(pat[r + 2, c + 1]), int(pat[r + 1, c]), int(pat[r + 1, c + 2])]
        if cur == k or cur in nb or breaks(r, c, cur):
            continue
        options = sorted({j for j in nb if j != k and present[r, c, j]}, key=nb.count, reverse=True)
        for j in options:
            if allowed(r, c, j) and delta(r, c, j) <= 1e-9:
                pat[r + 1, c + 1] = j
                break
    counts = obj.hist[2:-2, 2:-2].reshape(rows, 2, cols, 2, -1).sum((1, 3))
    _separate(pat, touch, ndimage.uniform_filter(counts, size=(3, 3, 1), mode="constant"), k)
    return pat[1:-1, 1:-1]


def _separate(pat: np.ndarray, touch: np.ndarray, around: np.ndarray, k: int) -> None:
    """残留的"不该相邻却相邻"（初稿带来的、优化没碰的）：用原图里隔在两者中间的那种墨补上。
    around[r, c, s]：这格周围 3×3 格里墨 s 有多少。补在那种墨更多的一格，一样多就补在留空的那格
    （保住有颜色的那格）；两格周围都没有那种墨就不动——原图那里确实没有东西隔着。"""
    rows, cols = around.shape[:2]
    for _ in range(2):
        fixed = 0
        for r in range(rows):
            for c in range(cols):
                a = int(pat[r + 1, c + 1])
                for dr, dc in ((0, 1), (1, 0)):
                    rr, cc = r + dr, c + dc
                    if rr >= rows or cc >= cols:
                        continue                        # 图外面不算邻居
                    b = int(pat[rr + 1, cc + 1])
                    if touch[a, b]:
                        continue
                    seps = [s for s in range(k) if touch[a, s] and touch[s, b]]
                    here = [(around[r, c, s], a == k, s, (r, c)) for s in seps if around[r, c, s] > 0]
                    here += [(around[rr, cc, s], b == k, s, (rr, cc)) for s in seps
                             if around[rr, cc, s] > 0]
                    if here:
                        _, _, s, (pr, pc) = max(here)
                        pat[pr + 1, pc + 1] = s
                        fixed += 1
                        a = int(pat[r + 1, c + 1])
        if not fixed:
            break
