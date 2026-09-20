from __future__ import annotations

from collections import deque

import numpy as np
from scipy import ndimage

from app.core.types import EMPTY, Issue, Report

_CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)
_N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _inside(grid, r, c):
    return 0 <= r < grid.shape[0] and 0 <= c < grid.shape[1]


def _empty_neighbors(grid, cells):
    out = []
    seen = set()
    for r, c in cells:
        for dr, dc in _N4:
            rr, cc = r + dr, c + dc
            if _inside(grid, rr, cc) and grid[rr, cc] == EMPTY and (rr, cc) not in seen:
                seen.add((rr, cc))
                out.append((rr, cc))
    return out


def _bfs_path(grid: np.ndarray, sources: set, targets: set) -> list[tuple[int, int]]:
    """从 sources 经空格到 targets 的最短路径（不含首尾填充格）。"""
    prev: dict[tuple[int, int], tuple[int, int] | None] = {}
    dq = deque()
    for s in sources:
        dq.append(s)
        prev[s] = None
    while dq:
        r, c = dq.popleft()
        for dr, dc in _N4:
            nxt = (r + dr, c + dc)
            if not _inside(grid, *nxt) or nxt in prev:
                continue
            if nxt in targets:
                path = []
                cur: tuple[int, int] | None = (r, c)
                while cur is not None and cur not in sources:
                    path.append(cur)
                    cur = prev[cur]
                return path[::-1]
            if grid[nxt] == EMPTY:
                prev[nxt] = (r, c)
                dq.append(nxt)
    return []


def attach_patches(report: Report, grid: np.ndarray, clear_index: int | None) -> Report:
    filled = grid != EMPTY
    lab4, n4 = ndimage.label(filled, structure=_CROSS)
    biggest = 0
    if n4 > 0:
        sizes = ndimage.sum(filled, lab4, index=range(1, n4 + 1))
        biggest = int(np.argmax(sizes)) + 1
    can_clear = clear_index is not None

    for issue in report.issues:
        t = issue.type
        if t == "isolated_bead":
            r, c = issue.cells[0]
            diag = [(r + dr, c + dc) for dr in (-1, 1) for dc in (-1, 1)
                    if _inside(grid, r + dr, c + dc) and grid[r + dr, c + dc] != EMPTY]
            if diag and can_clear:
                dr, dc = diag[0][0] - r, diag[0][1] - c
                cand = [(r + dr, c), (r, c + dc)]
                issue.action = "bridge_with_clear"
                issue.patch_cells = [cand[0] if grid[cand[0]] == EMPTY else cand[1]]
            else:
                issue.action, issue.patch_cells = "remove", [issue.cells[0]]
        elif t == "diagonal_link":
            (r1, c1), (r2, c2) = sorted(issue.cells)
            corner = (r1, c2) if grid[r1, c2] == EMPTY else (r2, c1)
            if can_clear:
                issue.action, issue.patch_cells = "bridge_with_clear", [corner]
            else:
                issue.action, issue.patch_cells = "remove", [issue.cells[0]]
        elif t == "thin_line":
            if can_clear:
                issue.action, issue.patch_cells = "bridge_with_clear", _empty_neighbors(grid, issue.cells)
            else:
                issue.action, issue.patch_cells = "none", []
        elif t == "hole":
            if can_clear:
                issue.action, issue.patch_cells = "fill_with_clear", list(issue.cells)
            else:
                issue.action, issue.patch_cells = "none", []
        elif t == "small_color":
            issue.action, issue.patch_cells = "merge_color", list(issue.cells)
        elif t == "disconnected":
            targets = set(map(tuple, np.argwhere(lab4 == biggest).tolist()))
            path = _bfs_path(grid, set(issue.cells), targets) if can_clear else []
            if path:
                issue.action, issue.patch_cells = "bridge_with_clear", path
            else:
                issue.action, issue.patch_cells = "remove", list(issue.cells)
    return report


def apply_patch(grid: np.ndarray, issue: Issue, clear_index: int | None) -> np.ndarray:
    out = grid.copy()
    if issue.action in ("bridge_with_clear", "fill_with_clear"):
        if clear_index is None:
            return out
        for r, c in issue.patch_cells:
            out[r, c] = clear_index
    elif issue.action == "remove":
        for r, c in issue.patch_cells:
            out[r, c] = EMPTY
    elif issue.action == "merge_color" and issue.target_color is not None:
        for r, c in issue.patch_cells:
            out[r, c] = issue.target_color
    return out
