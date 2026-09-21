from __future__ import annotations

import cv2
import numpy as np

from app.core import background, detect, downsample, face, fidelity, flat, image_io
from app.core.assign import assign_labels
from app.core.buildability import analyze
from app.core.color import pairwise_delta_e, srgb_to_lab, srgb_to_oklab
from app.core.merge import color_counts, detect_outline_cells, merge_small_colors
from app.core.palette import Palette
from app.core.patches import attach_patches
from app.core.select import rescue_salient_colors, select_palette
from app.core.types import EMPTY, Params, PatternResult


def _cell_lab(cell_rgb: np.ndarray) -> np.ndarray:
    return srgb_to_lab(cell_rgb)


def _load(image) -> np.ndarray:
    if isinstance(image, (bytes, bytearray)):
        return image_io.load_rgba(bytes(image))
    return np.asarray(image, dtype=np.float32)


#: 原图太小（每格不到这么多像素）时先平滑放大。128px 的图出 58 格，每格只有 2 个像素，
#: 抗锯齿像素和实打实的颜色一样多，逐像素投票的结果边缘毛糙、冒杂色。
MIN_PX_PER_CELL = 4
BORDER_TOLERANCE = 0.05


def _upscale_small(rgba: np.ndarray, long_side: int) -> np.ndarray:
    h, w = rgba.shape[:2]
    factor = int(np.ceil(MIN_PX_PER_CELL * long_side / max(h, w)))
    if factor <= 1:
        return rgba
    up = cv2.resize(rgba.astype(np.float32), (w * factor, h * factor), interpolation=cv2.INTER_CUBIC)
    return np.clip(up, 0.0, 1.0)


def _detect_flat(rgba: np.ndarray, long_side: int):
    """认墨，返回 (墨, 取色用的图)。只有平涂图才放大：照片按面积平均，放大只会更糊（实测还原度 -0.7）。
    先在原图上认（放大会把小色块的颜色抹花，认不出来），认不出再在放大的图上试一次（细线放大后才有实心像素）。"""
    up = _upscale_small(rgba, long_side)
    inks = flat.detect_inks(rgba)
    if inks is None and up is not rgba:
        inks = flat.detect_inks(up)
    return inks, (up if inks is not None else rgba)


def _downsample(rgba: np.ndarray, params: Params):
    """返回 (格子, 类型, 实际用来取色的图)。"""
    info = detect.detect_pixel_grid(rgba)
    if info is not None:
        return downsample.downsample_mode(rgba, info), "pixel_art", rgba
    inks, rgba = _detect_flat(rgba, params.grid_long_side)
    rows, cols = downsample.grid_shape(rgba.shape[0], rgba.shape[1], params.grid_long_side)
    cells = downsample.downsample_area(rgba, rows, cols)
    # 平涂插画：每格取原图自己的一种颜色，不要抗锯齿和缩小混出来的过渡色（见 core/flat.py）
    if inks is not None:
        cells = flat.downsample_inks(rgba, rows, cols, inks, cells.coverage)
    return cells, "image", rgba


def _flat_palette(cells, palette: Palette, max_colors: int) -> np.ndarray | None:
    """平涂插画：原图有哪几种颜色是知道的，每种直接配色卡里最接近的色号（ΔE2000）。
    k-medoids 会把两种相近的颜色并成一种（猫样图：腮红和鼻子两种粉并成 F9，腮红色差 9.5，
    而色卡里有 6.7 的 F14）。颜色种数超过用户设的上限时才退回 k-medoids 去取舍。"""
    if cells.inks is None or len(cells.inks) == 0:
        return None
    de = pairwise_delta_e(srgb_to_lab(cells.inks.astype(np.float64)), palette.lab)
    if palette.clear_index is not None:
        de[:, palette.clear_index] = np.inf              # 透明豆不是颜色
    working = np.unique(de.argmin(1))
    return working if len(working) <= max_colors else None


def _prepare(image, params: Params) -> np.ndarray:
    """读图 + 去背景：出图和算还原度看的是同一张图。"""
    rgba = _load(image)
    if params.background_seed is not None:
        return background.remove_background(rgba, params.background_seed,
                                            params.background_tolerance)
    if params.remove_background:
        # 边缘一圈是纯色时，把和边缘连通的那片背景去掉、不填豆；照片边缘不统一，自动跳过
        # 容差收紧到 BORDER_TOLERANCE：默认的 0.08 是给"点一下选背景"用的，自动去背景用它会把
        # 挨着白底的浅色也当成背景吃掉（彩虹旁边的浅蓝云朵整个消失）。边缘的抗锯齿过渡不靠容差，
        # 取色时会归回背景（flat.label_source）。
        rgba, _ = background.remove_border_background(
            rgba, min(params.background_tolerance, BORDER_TOLERANCE))
    return rgba


def measure_fidelity(image, params: Params, grid: np.ndarray, palette: Palette) -> dict | None:
    """给一张已有的图纸（比如手改过的）重新算还原度。算不了返回 None，不拖垮别的流程。"""
    try:
        rgba = _prepare(image, params)
        if detect.detect_pixel_grid(rgba) is not None:
            inks = None
        else:
            inks, rgba = _detect_flat(rgba, params.grid_long_side)
        return fidelity.measure(rgba, grid, palette.rgb, inks)
    except Exception:
        return None


def run(image, params: Params, palette: Palette | None = None) -> PatternResult:
    palette = palette or Palette.load(params.palette_id)
    rgba = _prepare(image, params)

    cells, kind, rgba = _downsample(rgba, params)
    rows, cols = cells.mask.shape
    grid = np.full((rows, cols), EMPTY, dtype=np.int16)
    if not cells.mask.any():
        return PatternResult(grid, [], {}, None, params, kind, cells.rgb)

    lab = _cell_lab(cells.rgb)
    ok = srgb_to_oklab(cells.rgb)
    working = _flat_palette(cells, palette, params.max_colors)
    if working is None:
        working = select_palette(ok[cells.mask], palette.oklab, k=params.max_colors)
    # 给嘴唇这类"小而显眼"、被 k-medoids 漏掉的颜色补名额（不突破 max_colors）
    working, rescued = rescue_salient_colors(ok, cells.mask, palette.oklab, working,
                                             max_colors=params.max_colors)
    k = len(working)
    cost = pairwise_delta_e(lab.reshape(-1, 3), palette.lab[working]).reshape(rows, cols, k)

    locked = -np.ones((rows, cols), dtype=np.int64)
    if params.lock_outlines:
        darkest = int(np.argmin(palette.lab[working][:, 0]))
        locked[detect_outline_cells(cells.rgb, cells.mask)] = darkest
    for r, c in params.protected_cells:
        if 0 <= r < rows and 0 <= c < cols and cells.mask[r, c]:
            locked[r, c] = int(np.argmin(cost[r, c]))

    # 五官开小灶：眼睛、鼻子、嘴巴周围原图反差明显的边罚得轻，单格瞳孔、鼻孔不被当杂点抹掉。
    # 像素图输入不做：那本来就是一格一格画好的，不需要也检测不准。检测失败时 faces=[]，一切照旧。
    faces = [] if kind == "pixel_art" else face.detect_faces(rgba)
    edge_weight = face.feature_edge_weights(faces, lab, cells.mask)
    local = assign_labels(cost, cells.mask, params.smoothness, locked, edge_weight=edge_weight)
    grid[cells.mask] = working[local[cells.mask]]

    protected_colors = {int(grid[r, c]) for r, c in params.protected_cells
                        if 0 <= r < rows and 0 <= c < cols and grid[r, c] != EMPTY}
    if palette.clear_index is not None:
        protected_colors.add(palette.clear_index)
    # 补进来的特征色往往只有几颗豆，低于小色号阈值也不能合并掉——那正是人眼最先看的地方
    protected_colors.update(rescued)
    if cells.flat:
        # 平涂插画：图纸上每种颜色都是原图真有的（没有过渡色可并）。只有两颗豆的眼睛高光
        # 并掉就是少了高光——还原度优先，不合并
        protected_colors.update(int(c) for c in np.unique(grid[cells.mask]))
    grid, _ = merge_small_colors(grid, palette.lab, params.small_color_threshold,
                                 protected=protected_colors)

    try:                     # 还原度是附加环节，失败不能拖垮出图
        fid = fidelity.measure(rgba, grid, palette.rgb, cells.inks)
    except Exception:
        fid = None
    return _finish(grid, cells.rgb, params, palette, kind, faces, fid)


def _finish(grid, cell_rgb, params: Params, palette: Palette, kind: str,
            faces: list | None = None, fid: dict | None = None) -> PatternResult:
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
                         params=params, input_kind=kind, cell_rgb=cell_rgb, faces=faces or [],
                         fidelity=fid)


def apply_edits(result: PatternResult, edits: list[tuple[int, int, int]],
                palette: Palette) -> PatternResult:
    grid = result.grid.copy()
    for r, c, v in edits:
        grid[r, c] = v
    return _finish(grid, result.cell_rgb, result.params, palette, result.input_kind, result.faces)


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
        # 行列一并给出：按钮上只写"58 格"看不出另一边多少，得标成"58×44"
        out.append({"long_side": n, "rows": rows, "cols": cols, "detail_loss": round(loss, 6)})
    return out
