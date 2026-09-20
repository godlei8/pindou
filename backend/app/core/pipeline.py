from __future__ import annotations

import cv2
import numpy as np

from app.core import background, detect, downsample, image_io
from app.core.assign import assign_labels
from app.core.buildability import analyze
from app.core.color import pairwise_delta_e, srgb_to_lab, srgb_to_oklab
from app.core.merge import color_counts, detect_outline_cells, merge_small_colors
from app.core.palette import Palette
from app.core.patches import attach_patches
from app.core.select import select_palette
from app.core.types import EMPTY, Params, PatternResult


def _cell_lab(cell_rgb: np.ndarray) -> np.ndarray:
    return srgb_to_lab(cell_rgb)


def _load(image) -> np.ndarray:
    if isinstance(image, (bytes, bytearray)):
        return image_io.load_rgba(bytes(image))
    return np.asarray(image, dtype=np.float32)


def _downsample(rgba: np.ndarray, params: Params):
    info = detect.detect_pixel_grid(rgba)
    if info is not None:
        return downsample.downsample_mode(rgba, info), "pixel_art"
    rows, cols = downsample.grid_shape(rgba.shape[0], rgba.shape[1], params.grid_long_side)
    return downsample.downsample_area(rgba, rows, cols), "image"


def run(image, params: Params, palette: Palette | None = None) -> PatternResult:
    palette = palette or Palette.load(params.palette_id)
    rgba = _load(image)
    if params.background_seed is not None:
        rgba = background.remove_background(rgba, params.background_seed, params.background_tolerance)

    cells, kind = _downsample(rgba, params)
    rows, cols = cells.mask.shape
    grid = np.full((rows, cols), EMPTY, dtype=np.int16)
    if not cells.mask.any():
        return PatternResult(grid, [], {}, None, params, kind, cells.rgb)

    lab = _cell_lab(cells.rgb)
    ok = srgb_to_oklab(cells.rgb)
    working = select_palette(ok[cells.mask], palette.oklab, k=params.max_colors)
    k = len(working)
    cost = pairwise_delta_e(lab.reshape(-1, 3), palette.lab[working]).reshape(rows, cols, k)

    locked = -np.ones((rows, cols), dtype=np.int64)
    if params.lock_outlines:
        darkest = int(np.argmin(palette.lab[working][:, 0]))
        locked[detect_outline_cells(cells.rgb, cells.mask)] = darkest
    for r, c in params.protected_cells:
        if 0 <= r < rows and 0 <= c < cols and cells.mask[r, c]:
            locked[r, c] = int(np.argmin(cost[r, c]))

    local = assign_labels(cost, cells.mask, params.smoothness, locked)
    grid[cells.mask] = working[local[cells.mask]]

    protected_colors = {int(grid[r, c]) for r, c in params.protected_cells
                        if 0 <= r < rows and 0 <= c < cols and grid[r, c] != EMPTY}
    if palette.clear_index is not None:
        protected_colors.add(palette.clear_index)
    grid, _ = merge_small_colors(grid, palette.lab, params.small_color_threshold,
                                 protected=protected_colors)

    return _finish(grid, cells.rgb, params, palette, kind)


def _finish(grid, cell_rgb, params: Params, palette: Palette, kind: str) -> PatternResult:
    counts = color_counts(grid)
    try:
        report = attach_patches(
            analyze(grid, palette.lab, params.small_color_threshold,
                    set(map(tuple, params.protected_cells)),
                    clear_index=palette.clear_index),
            grid, palette.clear_index)
    except Exception:       # 可拼性是附加环节，失败不能拖垮出图
        report = None
    working = [c for c, _ in sorted(counts.items(), key=lambda kv: -kv[1])]
    return PatternResult(grid=grid, working_palette=working, color_stats=counts, report=report,
                         params=params, input_kind=kind, cell_rgb=cell_rgb)


def apply_edits(result: PatternResult, edits: list[tuple[int, int, int]],
                palette: Palette) -> PatternResult:
    grid = result.grid.copy()
    for r, c, v in edits:
        grid[r, c] = v
    return _finish(grid, result.cell_rgb, result.params, palette, result.input_kind)


def suggest_sizes(image, base: int) -> list[dict]:
    """给 3 档格数各算一个"细节损失"分：把下采样结果按最近邻放大回原尺寸，与原图比 OKLab 均方差。

    放大必须用 cv2.resize 精确回到 (w, h)。早期版本用 np.repeat + 整除，
    余数靠 edge-pad 补，导致图像整体错位，且格数越大错位越严重、分数越离谱。
    """
    rgba = _load(image)
    ok_full = srgb_to_oklab(rgba[..., :3])
    h, w = rgba.shape[:2]
    out = []
    for n in (round(base * 0.75), base, round(base * 1.5)):
        rows, cols = downsample.grid_shape(h, w, n)
        cells = downsample.downsample_area(rgba, rows, cols, denoise=False)
        up = cv2.resize(cells.rgb, (w, h), interpolation=cv2.INTER_NEAREST)
        loss = float(np.mean((srgb_to_oklab(up) - ok_full) ** 2))
        out.append({"long_side": n, "detail_loss": round(loss, 6)})
    return out
