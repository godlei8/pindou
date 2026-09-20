from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.core.types import EMPTY


@dataclass(frozen=True)
class Board:
    row0: int
    col0: int
    rows: int
    cols: int
    label: str


def cut_cost(grid: np.ndarray, axis: int, pos: int) -> int:
    """切线在索引 pos 之前（pos-1 | pos）。axis=1 竖切（列），axis=0 横切（行）。"""
    if axis == 1:
        a, b = grid[:, pos - 1], grid[:, pos]
    else:
        a, b = grid[pos - 1, :], grid[pos, :]
    return int(((a == b) & (a != EMPTY)).sum())


def _cuts(grid: np.ndarray, axis: int, size: int, slack: int) -> list[int]:
    n = grid.shape[axis]
    cuts = [0]
    while n - cuts[-1] > size:
        lo, hi = cuts[-1] + max(1, size - slack), cuts[-1] + size
        best_pos, best_cost = hi, None
        for pos in range(lo, hi + 1):
            c = cut_cost(grid, axis, pos)
            if best_cost is None or c <= best_cost:
                best_pos, best_cost = pos, c
        cuts.append(best_pos)
    cuts.append(n)
    return cuts


def split_boards(grid: np.ndarray, board_rows: int, board_cols: int, slack: int = 3) -> list[Board]:
    row_cuts = _cuts(grid, 0, board_rows, slack)
    col_cuts = _cuts(grid, 1, board_cols, slack)
    boards = []
    for i in range(len(row_cuts) - 1):
        for j in range(len(col_cuts) - 1):
            r0, r1 = row_cuts[i], row_cuts[i + 1]
            c0, c1 = col_cuts[j], col_cuts[j + 1]
            boards.append(Board(r0, c0, r1 - r0, c1 - c0, f"{chr(ord('A') + i)}{j + 1}"))
    return boards
