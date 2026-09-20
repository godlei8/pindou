from __future__ import annotations

import numpy as np
from scipy import ndimage

from app.core.color import pairwise_delta_e
from app.core.merge import color_counts
from app.core.types import EMPTY, Issue, Report

_CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)

# 评分权重：每项扣分上限
_W = dict(disconnected=30.0, isolated=20.0, diagonal=15.0, thin=20.0, hole=10.0, small=10.0, confetti=25.0)


def _cells(mask: np.ndarray) -> list[tuple[int, int]]:
    r, c = np.nonzero(mask)
    return [(int(a), int(b)) for a, b in zip(r, c)]


def _same_color_neighbor_count(grid: np.ndarray) -> np.ndarray:
    pad = np.pad(grid, 1, constant_values=EMPTY)
    n = np.zeros(grid.shape, dtype=np.int32)
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nb = pad[1 + dr:1 + dr + grid.shape[0], 1 + dc:1 + dc + grid.shape[1]]
        n += ((nb == grid) & (grid != EMPTY)).astype(np.int32)
    return n


def _diagonal_pairs(filled: np.ndarray) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """仅对角接触、且两格无共同 4-邻居填充格的格子对。"""
    rows, cols = filled.shape
    pairs = []
    for r in range(rows - 1):
        for c in range(cols):
            for dc in (1, -1):
                c2 = c + dc
                if not (0 <= c2 < cols):
                    continue
                if filled[r, c] and filled[r + 1, c2] and not filled[r + 1, c] and not filled[r, c2]:
                    pairs.append(((r, c), (r + 1, c2)))
    return pairs


def analyze(grid: np.ndarray, palette_lab: np.ndarray, small_color_threshold: int = 10,
            protected_cells: set[tuple[int, int]] = frozenset()) -> Report:
    filled = grid != EMPTY
    n_cells = int(filled.sum())
    issues: list[Issue] = []
    prot = np.zeros(grid.shape, bool)
    for r, c in protected_cells:
        prot[r, c] = True

    # 连通性
    lab4, n4 = ndimage.label(filled, structure=_CROSS)
    if n4 > 1:
        sizes = ndimage.sum(filled, lab4, index=range(1, n4 + 1))
        biggest = int(np.argmax(sizes)) + 1
        for i in range(1, n4 + 1):
            if i != biggest:
                issues.append(Issue("disconnected", _cells(lab4 == i), "todo", severity=float(sizes[i - 1])))

    # 孤立单豆
    nb_filled = ndimage.convolve(filled.astype(np.int32), _CROSS.astype(np.int32), mode="constant") - filled
    isolated = filled & (nb_filled == 0) & ~prot
    for cell in _cells(isolated):
        issues.append(Issue("isolated_bead", [cell], "todo"))

    # 对角虚连
    diag = _diagonal_pairs(filled)
    for a, b in diag:
        issues.append(Issue("diagonal_link", [a, b], "todo"))

    # 细线
    thick = ndimage.binary_erosion(filled, structure=_CROSS, border_value=0)
    thin = filled & ~ndimage.binary_dilation(thick, structure=_CROSS)
    lab_thin, n_thin = ndimage.label(thin, structure=_CROSS)
    n_thin_cells = 0
    for i in range(1, n_thin + 1):
        cells = _cells(lab_thin == i)
        if len(cells) >= 3:
            issues.append(Issue("thin_line", cells, "todo", severity=float(len(cells))))
            n_thin_cells += len(cells)

    # 空洞
    lab_e, n_e = ndimage.label(~filled, structure=_CROSS)
    border = np.zeros(grid.shape, bool)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    border_labels = set(np.unique(lab_e[border & ~filled]).tolist())
    n_holes = 0
    for i in range(1, n_e + 1):
        if i not in border_labels:
            issues.append(Issue("hole", _cells(lab_e == i), "todo"))
            n_holes += 1

    # 小色号
    counts = color_counts(grid)
    small = [c for c, n in counts.items() if n < small_color_threshold]
    for c in small:
        others = [o for o in counts if o != c]
        target, de = None, None
        if others:
            d = pairwise_delta_e(palette_lab[[c]], palette_lab[others])[0]
            j = int(np.argmin(d))
            target, de = int(others[j]), float(d[j])
        issues.append(Issue("small_color", _cells(grid == c), "todo", target_color=target, delta_e=de))

    # confetti
    same = _same_color_neighbor_count(grid)
    confetti = filled & (same == 0) & ~prot
    confetti_pct = float(100.0 * confetti.sum() / n_cells) if n_cells else 0.0

    thin_ratio = n_thin_cells / n_cells if n_cells else 0.0
    n_iso = int(isolated.sum())
    metrics = dict(n_isolated=n_iso, n_diagonal=len(diag), thin_ratio=thin_ratio, n_holes=n_holes,
                   n_small_colors=len(small), n_colors=len(counts), n_cells=n_cells)

    score = 100.0
    if n4 > 1:
        score -= min(_W["disconnected"], 15.0 + 5.0 * (n4 - 1))
    score -= min(_W["isolated"], 2.0 * n_iso)
    score -= min(_W["diagonal"], 3.0 * len(diag))
    score -= _W["thin"] * min(1.0, thin_ratio)
    score -= min(_W["hole"], 2.0 * n_holes)
    score -= min(_W["small"], 2.0 * len(small))
    score -= _W["confetti"] * float(np.clip((confetti_pct - 2.0) / 8.0, 0.0, 1.0))
    score = float(max(0.0, round(score, 1)))

    return Report(score=score, confetti_pct=round(confetti_pct, 2), n_components=int(n4),
                  issues=issues, metrics=metrics)
