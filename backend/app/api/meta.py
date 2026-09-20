from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import Palette, StylePreset, User
from app.schemas import PaletteColorOut, PaletteOut, StylePresetOut
from app.services.palettes import load_core_palette

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/palettes", response_model=list[PaletteOut])
def list_palettes(user: User = Depends(current_user),
                  db: Session = Depends(get_db)) -> list[Palette]:
    return list(db.scalars(select(Palette).order_by(Palette.brand)).all())


@router.get("/palettes/{palette_id}/colors", response_model=list[PaletteColorOut])
def list_palette_colors(palette_id: str, user: User = Depends(current_user)) -> list[dict]:
    """按 core 色卡的**全局索引**返回——grid 里存的就是这个索引，前端要靠它上色。"""
    try:
        p = load_core_palette(palette_id)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"色卡不存在：{palette_id}") from None
    role_by_code = p.roles
    return [{"index": i, "code": p.codes[i], "name": p.names[i],
             "hex": "#{:02X}{:02X}{:02X}".format(*p.rgb[i]),
             "role": role_by_code.get(p.codes[i]), "confidence": p.confidence[i]}
            for i in range(len(p))]


@router.get("/style-presets", response_model=list[StylePresetOut])
def list_style_presets(user: User = Depends(current_user),
                       db: Session = Depends(get_db)) -> list[StylePreset]:
    return list(db.scalars(
        select(StylePreset).where(StylePreset.is_active.is_(True))
        .order_by(StylePreset.sort_order, StylePreset.name)).all())
