from __future__ import annotations

import hashlib
import io
import uuid
from dataclasses import fields as dc_fields

import numpy as np
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import pdf as core_pdf
from app.core import pipeline, render
from app.core.buildability import analyze
from app.core.merge import color_counts
from app.core.palette import Palette as CorePalette
from app.core.patches import apply_patch, attach_patches
from app.core.split import Board
from app.core.types import EMPTY, Issue, Params
from app.models import AiRender, Pattern, Project
from app.services.palettes import load_core_palette
from app.services.storage import get_storage

_LIMITS = {
    "grid_long_side": (8, 200),
    "max_colors": (2, 64),
    "smoothness": (0.0, 50.0),
    "small_color_threshold": (0, 1000),
    "background_tolerance": (0.0, 1.0),
}
_PARAM_KEYS = {f.name for f in dc_fields(Params)}


class PatternError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def storage_of():
    return get_storage()


def params_from_dict(d: dict) -> Params:
    clean = {k: v for k, v in (d or {}).items() if k in _PARAM_KEYS}
    for key, (lo, hi) in _LIMITS.items():
        if key in clean and clean[key] is not None:
            v = clean[key]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not (lo <= v <= hi):
                raise PatternError(f"参数 {key} 超出允许范围 [{lo}, {hi}]：{v!r}")
    if clean.get("protected_cells"):
        clean["protected_cells"] = [tuple(c) for c in clean["protected_cells"]]
    if clean.get("background_seed"):
        clean["background_seed"] = tuple(clean["background_seed"])
    try:
        return Params(**clean)
    except TypeError as e:
        raise PatternError(f"参数无法解析：{e}") from e


def params_to_dict(p: Params) -> dict:
    return p.to_dict()


def grid_to_db(grid: np.ndarray) -> list[list[int | None]]:
    return [[None if int(v) == EMPTY else int(v) for v in row] for row in grid]


def grid_from_db(grid: list) -> np.ndarray:
    return np.array([[EMPTY if v is None else int(v) for v in row] for row in grid],
                    dtype=np.int16)


def _analyze_report(grid: np.ndarray, palette: CorePalette, params: Params) -> dict | None:
    """可拼性是附加环节：任何异常都只让它变成 None，绝不让出图失败。"""
    try:
        report = attach_patches(
            analyze(grid, palette.lab, params.small_color_threshold,
                    set(map(tuple, params.protected_cells)),
                    clear_index=palette.clear_index),
            grid, palette.clear_index)
        return report.to_dict()
    except Exception:
        return None


def create_project(db: Session, user_id: uuid.UUID, name: str, image_bytes: bytes) -> Project:
    limit = get_settings().max_upload_bytes
    if len(image_bytes) > limit:
        raise PatternError(f"图片过大：{len(image_bytes)} 字节，上限 {limit}")
    try:
        probe = Image.open(io.BytesIO(image_bytes))
        probe.verify()
        fmt = (probe.format or "").upper()
    except (UnidentifiedImageError, OSError) as e:
        raise PatternError(f"无法识别的图片格式：{e}") from e
    if fmt not in {"PNG", "JPEG", "WEBP"}:
        raise PatternError(f"不支持的图片格式：{fmt or '未知'}，仅支持 PNG / JPEG / WEBP")

    key = hashlib.sha256(image_bytes).hexdigest()
    rel = storage_of().save("uploads", key, image_bytes, ".png" if fmt == "PNG" else ".bin")
    proj = Project(user_id=user_id, name=name.strip() or "未命名", source_image_path=rel)
    db.add(proj)
    db.flush()
    return proj


def _source_bytes(project: Project, ai_render: AiRender | None) -> bytes:
    st = storage_of()
    if ai_render is not None and ai_render.output_path:
        return st.load(ai_render.output_path)
    return st.load(project.source_image_path)


def generate(db: Session, project: Project, params: Params,
             ai_render: AiRender | None = None) -> Pattern:
    palette = load_core_palette(params.palette_id)
    result = pipeline.run(_source_bytes(project, ai_render), params, palette)
    pat = Pattern(
        project_id=project.id,
        ai_render_id=ai_render.id if ai_render is not None else None,
        origin="generated",
        params=params_to_dict(params),
        grid=grid_to_db(result.grid),
        color_stats={str(k): int(v) for k, v in result.color_stats.items()},
        buildability=_analyze_report(result.grid, palette, params),
    )
    db.add(pat)
    db.flush()
    return pat


def _child(db: Session, parent: Pattern, grid: np.ndarray, palette: CorePalette,
           params: Params, origin: str, **extra) -> Pattern:
    child = Pattern(
        project_id=parent.project_id, ai_render_id=parent.ai_render_id, parent_id=parent.id,
        origin=origin, params=parent.params, grid=grid_to_db(grid),
        color_stats={str(k): int(v) for k, v in color_counts(grid).items()},
        buildability=_analyze_report(grid, palette, params), **extra)
    db.add(child)
    db.flush()
    return child


def apply_issue(db: Session, pattern: Pattern, issue_index: int) -> Pattern:
    if not pattern.buildability or not pattern.buildability.get("issues"):
        raise PatternError("这张图纸没有可应用的修复建议")
    issues = pattern.buildability["issues"]
    if not (0 <= issue_index < len(issues)):
        raise PatternError(f"修复建议序号越界：{issue_index}")
    raw = issues[issue_index]
    params = params_from_dict(pattern.params)
    palette = load_core_palette(params.palette_id)
    issue = Issue(
        type=raw["type"], cells=[tuple(c) for c in raw["cells"]], action=raw["action"],
        target_color=raw.get("target_color"), delta_e=raw.get("delta_e"),
        patch_cells=[tuple(c) for c in raw.get("patch_cells", [])],
        severity=raw.get("severity", 1.0))
    new_grid = apply_patch(grid_from_db(pattern.grid), issue, palette.clear_index)
    return _child(db, pattern, new_grid, palette, params, "patched", applied_patch=raw)


def apply_manual_edits(db: Session, pattern: Pattern, edits: list[dict],
                       protected_cells: list[list[int]] | None = None) -> Pattern:
    """按显式格子列表写入。后端不重放油漆桶等填充算法——前端提交的是结果，不是操作意图。"""
    if not edits:
        raise PatternError("改动集为空")
    params = params_from_dict(pattern.params)
    palette = load_core_palette(params.palette_id)
    grid = grid_from_db(pattern.grid)
    rows, cols = grid.shape
    recorded = []
    for e in edits:
        try:
            r, c = int(e["cell"][0]), int(e["cell"][1])
        except (KeyError, IndexError, TypeError, ValueError) as ex:
            raise PatternError(f"改动项格式错误：{e!r}") from ex
        if not (0 <= r < rows and 0 <= c < cols):
            raise PatternError(f"格子越界：({r}, {c})，图纸尺寸 {rows}×{cols}")
        to = e.get("to")
        if to is not None:
            to = int(to)
            if not (0 <= to < len(palette)):
                raise PatternError(f"未知色号索引：{to}")
        recorded.append({"cell": [r, c],
                         "from": None if grid[r, c] == EMPTY else int(grid[r, c]),
                         "to": to})
        grid[r, c] = EMPTY if to is None else to

    if protected_cells is not None:
        params.protected_cells = [tuple(c) for c in protected_cells]
    return _child(db, pattern, grid, palette, params, "edited", manual_edits=recorded)


def materials_of(pattern: Pattern, palette: CorePalette, pack_size: int = 1000) -> list[dict]:
    return render.materials(grid_from_db(pattern.grid), palette, pack_size=pack_size)


def export_png(pattern: Pattern, palette: CorePalette, cell_px: int = 28,
               board: Board | None = None) -> bytes:
    img = render.render_grid(grid_from_db(pattern.grid), palette,
                             render.RenderOptions(cell_px=cell_px, board=board))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def export_pdf(pattern: Pattern, palette: CorePalette, bead_mm: float = 5.0) -> bytes:
    return core_pdf.render_pdf(grid_from_db(pattern.grid), palette,
                               core_pdf.PdfOptions(bead_mm=bead_mm))
