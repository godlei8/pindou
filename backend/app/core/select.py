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
