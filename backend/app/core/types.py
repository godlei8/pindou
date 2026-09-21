from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np

EMPTY = -1  # 网格空格


@dataclass
class Params:
    grid_long_side: int = 58          # 长边格数
    max_colors: int = 24
    smoothness: float = 2.0           # graph cut λ；0 = 纯最近色。默认值由 scripts/benchmark.py
                                      # 在 10 张黄金样本上比较 λ∈{0,1,2,3} 选出：2.0 在每张图上
                                      # 的 confetti 都不劣于 1.0 且不损失色数；3.0 开始吃掉色号。
    dither: bool = False
    palette_id: str = "mard"
    background_seed: tuple[int, int] | None = None   # 吸管点 (x, y)，原图坐标
    background_tolerance: float = 0.08               # OKLab 距离
    #: 自动去掉纯色背景（边缘一圈几乎同色时，背景不填豆）。算法层默认关，
    #: 保证旧图纸（参数里没有这个键）的含义不变；产品默认值在前端 DEFAULT_PARAMS 里开。
    remove_background: bool = False
    small_color_threshold: int = 10                  # 少于此颗数的色号建议合并
    protected_cells: list[tuple[int, int]] = field(default_factory=list)  # (row, col)
    lock_outlines: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Issue:
    type: str                          # isolated_bead / diagonal_link / thin_line / hole / small_color / disconnected
    cells: list[tuple[int, int]]       # 涉及格子 (row, col)
    action: str                        # bridge_with_clear / merge_to_neighbor / merge_color / fill_with_clear / remove
    target_color: int | None = None    # 全局色卡索引
    delta_e: float | None = None
    patch_cells: list[tuple[int, int]] = field(default_factory=list)  # apply 时实际改动的格子
    severity: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Report:
    score: float
    confetti_pct: float
    n_components: int
    issues: list[Issue]
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PatternResult:
    grid: np.ndarray                    # int16 (rows, cols)，-1 = 空
    working_palette: list[int]          # 本图用到的全局色卡索引
    color_stats: dict[int, int]         # 全局索引 → 颗数
    report: Report | None
    params: Params
    input_kind: str                     # "image" | "pixel_art"
    cell_rgb: np.ndarray | None = None  # (rows, cols, 3) 下采样后的 sRGB 0–1，供调试/预览
    faces: list = field(default_factory=list)   # 检测到的人脸（core.face.Face），用来提示脸太小
    fidelity: dict | None = None        # 还原度（core.fidelity.measure），第一优先的指标

    def grid_as_list(self) -> list[list[int | None]]:
        return [[None if v == EMPTY else int(v) for v in row] for row in self.grid]
