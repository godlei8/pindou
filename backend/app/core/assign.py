from __future__ import annotations

import maxflow
import numpy as np

_LOCK_PENALTY = 1e6


def _edges(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """返回 4-邻域内、两端都在 mask 内的边 (p_idx, q_idx)，索引为展平后的节点号。"""
    rows, cols = mask.shape
    idx = np.arange(rows * cols).reshape(rows, cols)
    h_ok = mask[:, :-1] & mask[:, 1:]
    v_ok = mask[:-1, :] & mask[1:, :]
    p = np.concatenate([idx[:, :-1][h_ok], idx[:-1, :][v_ok]])
    q = np.concatenate([idx[:, 1:][h_ok], idx[1:, :][v_ok]])
    return p, q


def energy(cost: np.ndarray, mask: np.ndarray, labels: np.ndarray, smoothness: float,
           edge_weight: np.ndarray | None = None) -> float:
    r, c = np.nonzero(mask)
    data = cost[r, c, labels[r, c]].sum()
    p, q = _edges(mask)
    flat = labels.ravel()
    w = smoothness if edge_weight is None else smoothness * edge_weight
    pair = (w * (flat[p] != flat[q])).sum()
    return float(data + pair)


def assign_labels(cost: np.ndarray, mask: np.ndarray, smoothness: float,
                  locked: np.ndarray | None = None, n_sweeps: int = 3,
                  edge_weight: np.ndarray | None = None) -> np.ndarray:
    """α-expansion 图割。

    edge_weight：每条边的平滑强度倍数（顺序同 _edges(mask)），不给就全是 1——
    和原来完全一样。用来给五官"开小灶"：五官周围原图反差明显的边罚得轻，
    单格瞳孔、鼻孔就不会被当成杂点抹掉。倍数必须 ≥ 0，Potts 模型下 α-expansion 仍然成立。"""
    rows, cols, k = cost.shape
    cost = cost.astype(np.float64).copy()
    if locked is not None:
        lr, lc = np.nonzero(locked >= 0)
        for r, c in zip(lr, lc):
            j = locked[r, c]
            cost[r, c] += _LOCK_PENALTY
            cost[r, c, j] -= _LOCK_PENALTY
    labels = np.where(mask, cost.argmin(axis=-1), -1).astype(np.int64)
    if smoothness <= 0 or k == 1:
        return labels

    p, q = _edges(mask)
    if edge_weight is not None and len(edge_weight) != len(p):
        raise ValueError(f"edge_weight 长度 {len(edge_weight)} 与边数 {len(p)} 不符")
    lam = smoothness if edge_weight is None else smoothness * np.asarray(edge_weight, float)
    flat_mask = mask.ravel()
    flat_cost = cost.reshape(-1, k)
    node_ix = np.arange(rows * cols)
    cur_energy = energy(cost, mask, labels, smoothness, edge_weight)

    for _ in range(n_sweeps):
        improved = False
        for alpha in range(k):
            f = labels.ravel()
            U0 = np.where(flat_mask, flat_cost[node_ix, np.maximum(f, 0)], 0.0)
            U1 = np.where(flat_mask, cost[..., alpha].ravel(), 0.0)
            U1 = np.where(f == alpha, U0, U1).copy()
            A = lam * (f[p] != f[q])
            B = lam * (f[p] != alpha)
            C = lam * (alpha != f[q])
            np.add.at(U1, p, C - A)
            np.add.at(U1, q, -C)             # D - C，D = 0
            w = B + C - A                    # Potts 下 >= 0
            g = maxflow.GraphFloat()
            ids = g.add_grid_nodes((rows, cols))
            g.add_grid_tedges(ids, U1.reshape(rows, cols), U0.reshape(rows, cols))
            if len(p):
                g.add_edges(p.astype(np.int32), q.astype(np.int32), w, np.zeros_like(w))
            g.maxflow()
            switch = g.get_grid_segments(ids).ravel() & flat_mask   # sink 侧 = 取 alpha
            new = f.copy()
            new[switch] = alpha
            new_labels = new.reshape(rows, cols)
            e = energy(cost, mask, new_labels, smoothness, edge_weight)
            if e < cur_energy - 1e-9:
                labels, cur_energy, improved = new_labels, e, True
        if not improved:
            break
    return labels
