from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.palette import Palette as CorePalette
from app.db import get_db
from app.models import Feedback, Pattern, Project, User
from app.schemas import EditIn, FeedbackIn, PatchIn
from app.services import patterns as psvc
from app.services.palettes import load_core_palette

router = APIRouter(prefix="/api/patterns", tags=["patterns"])


def _owned_pattern(db: Session, user: User, pattern_id: uuid.UUID) -> Pattern:
    pat = db.get(Pattern, pattern_id)
    if pat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "图纸不存在")
    proj = db.get(Project, pat.project_id)
    if proj is None or proj.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "图纸不存在")
    return pat


def pattern_out(pat: Pattern, palette: CorePalette) -> dict:
    return {
        "id": pat.id, "project_id": pat.project_id, "parent_id": pat.parent_id,
        "origin": pat.origin, "ai_render_id": pat.ai_render_id,
        "params": pat.params, "grid": pat.grid,
        "color_stats": pat.color_stats, "buildability": pat.buildability,
        "materials": psvc.materials_of(pat, palette),
        "palette_id": (pat.params or {}).get("palette_id", "mard"),
        "created_at": pat.created_at,
    }


def _palette_of(pat: Pattern) -> CorePalette:
    return load_core_palette((pat.params or {}).get("palette_id", "mard"))


@router.get("/{pattern_id}")
def get_pattern(pattern_id: uuid.UUID, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> dict:
    pat = _owned_pattern(db, user, pattern_id)
    return pattern_out(pat, _palette_of(pat))


@router.post("/{pattern_id}/apply-patch")
def apply_patch_endpoint(pattern_id: uuid.UUID, body: PatchIn,
                         user: User = Depends(current_user),
                         db: Session = Depends(get_db)) -> dict:
    pat = _owned_pattern(db, user, pattern_id)
    child = psvc.apply_issue(db, pat, body.issue_index)
    db.commit()
    return pattern_out(child, _palette_of(child))


@router.post("/{pattern_id}/edits")
def apply_edits_endpoint(pattern_id: uuid.UUID, body: EditIn,
                         user: User = Depends(current_user),
                         db: Session = Depends(get_db)) -> dict:
    pat = _owned_pattern(db, user, pattern_id)
    child = psvc.apply_manual_edits(db, pat, [e.model_dump() for e in body.edits],
                                    body.protected_cells)
    db.commit()
    return pattern_out(child, _palette_of(child))


@router.post("/{pattern_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
def add_feedback(pattern_id: uuid.UUID, body: FeedbackIn,
                 user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    pat = _owned_pattern(db, user, pattern_id)
    db.add(Feedback(pattern_id=pat.id, user_id=user.id, kind=body.kind,
                    cells=body.cells, note=body.note))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{pattern_id}/export")
def export(pattern_id: uuid.UUID, format: str = Query("png"),
           cell_px: int = Query(28, ge=4, le=120), bead_mm: float = Query(5.0, gt=0, le=20),
           user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    pat = _owned_pattern(db, user, pattern_id)
    palette = _palette_of(pat)
    if format == "png":
        return Response(
            psvc.export_png(pat, palette, cell_px=cell_px), media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="pattern-{pat.id}.png"'})
    if format == "pdf":
        return Response(
            psvc.export_pdf(pat, palette, bead_mm=bead_mm), media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="pattern-{pat.id}.pdf"'})
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"不支持的导出格式：{format}")
