from __future__ import annotations

import numpy as np


def select_palette(cell_oklab: np.ndarray, palette_oklab: np.ndarray, k: int,
                   weights: np.ndarray | None = None, seed: int = 0, max_iter: int = 30) -> np.ndarray:
    m = cell_oklab.shape[0]
    n = palette_oklab.shape[0]
    if m == 0:
        return np.zeros(0, dtype=np.int64)
    k = max(1, min(k, n))
    w = np.ones(m) if weights is None else np.asarray(weights, dtype=np.float64)
    diff = cell_oklab[:, None, :] - palette_oklab[None, :, :]
    D = np.einsum("ijk,ijk->ij", diff, diff)            # (m, n) 平方距离
    rng = np.random.default_rng(seed)

    # k-means++ 风格初始化，候选限于色卡
    chosen = [int(np.argmin(D[rng.integers(m)]))]
    while len(chosen) < k:
        best_now = D[:, chosen].min(axis=1)
        if best_now.sum() <= 0:
            break
        p = best_now * w
        total = p.sum()
        if total <= 0:
            break
        p = p / total
        cell = rng.choice(m, p=p)
        cand = int(np.argmin(D[cell]))
        if cand in chosen:
            order = np.argsort(D[cell])
            cand = next((int(c) for c in order if int(c) not in chosen), None)
            if cand is None:
                break
        chosen.append(cand)

    cur = np.array(chosen, dtype=np.int64)
    for _ in range(max_iter):
        assign = cur[np.argmin(D[:, cur], axis=1)]        # 每格所属的全局色卡索引
        new: list[int] = []
        for c in cur:
            members = assign == c
            if not members.any():
                continue
            cost = (w[members, None] * D[members]).sum(axis=0)   # 对全部色卡列
            best = int(np.argmin(cost))
            if best not in new:
                new.append(best)
        new_arr = np.array(new, dtype=np.int64)
        if len(new_arr) == len(cur) and set(new_arr.tolist()) == set(cur.tolist()):
            cur = new_arr
            break
        cur = new_arr
    assign = cur[np.argmin(D[:, cur], axis=1)]
    sizes = np.array([(w * (assign == c)).sum() for c in cur])
    return cur[np.argsort(-sizes)]


#: OKLab 距离超过这个值就算"明显是错的颜色"（约 3 倍恰可察觉差）。
#: 在真实人像上校准：嘴唇到最近可用色 0.068，全图 99% 分位 0.057；
#: 取 0.06 时全图只有嘴唇一块被选中，取 0.05 就会把背景灯光光斑也卷进来。
SALIENT_FAR = 0.06
#: 至少这么多格连成一片才算"特征"；零星一两格是噪点，不值得占一个色号
SALIENT_MIN_CELLS = 3
#: 两个已选色离得比这还近就算"几乎重复"，可以腾一个出来（真实人像里 M15/M3 只差 0.018）
DUPLICATE_NEAR = 0.025


def rescue_salient_colors(cell_ok: np.ndarray, mask: np.ndarray, palette_ok: np.ndarray,
                          working: np.ndarray, max_colors: int,
                          far: float = SALIENT_FAR, min_cells: int = SALIENT_MIN_CELLS,
                          duplicate: float = DUPLICATE_NEAR,
                          max_rescues: int = 3) -> tuple[np.ndarray, list[int]]:
    """给"小而显眼"的颜色补一个名额。返回 (新的工作色板, 补进来的色卡索引)。

    k-medoids 最小化全图总误差，每格权重一样。嘴唇这类特征只占十几格，
    会被拆进周围大片褐色、粉色的簇里当少数派，簇的代表色向多数漂移，
    最后没有一个颜色是给它的——而这偏偏是人眼最先看的地方。

    找法：离所有已选色都很远（> far）、且连成一片（≥ min_cells 格）的区域，
    就是被漏掉的特征。给它色卡里最合适的那个色：
    - 没到 max_colors 上限就直接加；
    - 到了上限，就从一对几乎重复的已选色（< duplicate）里拿掉用得少的那个腾出名额；
    - 腾不出来就不补——用户设的"最多色数"是硬上限。
    """
    from scipy import ndimage

    working = [int(c) for c in working]
    rescued: list[int] = []
    if not mask.any():
        return np.array(working, dtype=np.int64), rescued

    def nearest_dist(colors: list[int]) -> np.ndarray:
        W = palette_ok[colors]
        d2 = ((cell_ok[..., None, :] - W[None, None]) ** 2).sum(-1)
        return np.sqrt(d2.min(-1))

    d = nearest_dist(working)
    bad = (d > far) & mask
    labels, n = ndimage.label(bad)          # 4-连通
    if n == 0:
        return np.array(working, dtype=np.int64), rescued
    comps = [np.argwhere(labels == i + 1) for i in range(n)]
    comps = [c for c in comps if len(c) >= min_cells]
    # 最显眼的先来：格数 × 离得多远
    comps.sort(key=lambda c: -float(d[c[:, 0], c[:, 1]].sum()))

    for comp in comps:
        if len(rescued) >= max_rescues:
            break
        px = cell_ok[comp[:, 0], comp[:, 1]]
        cur = np.sqrt(((px[:, None] - palette_ok[working][None]) ** 2).sum(-1)).min(1)
        if cur.mean() <= far:               # 前面补的色已经顺带照顾到它了
            continue
        dist_all = np.sqrt(((px[:, None] - palette_ok[None]) ** 2).sum(-1))   # (格, 色卡)
        best = int(dist_all.mean(0).argmin())
        if dist_all[:, best].mean() > far:  # 色卡里也没有接近的颜色，补了也白补
            continue
        if best in working:
            continue
        if len(working) >= max_colors:
            victim = _near_duplicate_to_drop(cell_ok, mask, palette_ok, working, duplicate)
            if victim is None:
                break                       # 名额都是实打实用着的，不突破上限
            working.remove(victim)
        working.append(best)
        rescued.append(best)
    return np.array(working, dtype=np.int64), rescued


def _near_duplicate_to_drop(cell_ok, mask, palette_ok, working, duplicate) -> int | None:
    """最接近的一对已选色如果几乎重复，返回其中用得少的那个；否则 None。"""
    W = palette_ok[working]
    pd = np.sqrt(((W[:, None] - W[None]) ** 2).sum(-1))
    np.fill_diagonal(pd, np.inf)
    i, j = np.unravel_index(int(pd.argmin()), pd.shape)
    if pd[i, j] >= duplicate:
        return None
    owner = ((cell_ok[mask][:, None] - W[None]) ** 2).sum(-1).argmin(1)
    use_i, use_j = int((owner == i).sum()), int((owner == j).sum())
    return working[i] if use_i <= use_j else working[j]
