from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.color import srgb_to_lab
from app.core.palette import Palette as CorePalette
from app.models import Palette, PaletteColor

_PALETTE_DIR = Path(__file__).resolve().parents[1] / "palettes"


@lru_cache
def load_core_palette(palette_id: str = "mard") -> CorePalette:
    """供流水线使用的色卡。直接读 JSON，不查库——core 不许依赖数据库。"""
    return CorePalette.load(palette_id)


def seed_palettes(db: Session) -> int:
    """把 app/palettes/*.json 灌进库。同 brand+version 已存在则跳过，返回新增色数。"""
    written = 0
    for path in sorted(_PALETTE_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        exists = db.scalar(
            select(Palette).where(Palette.brand == doc["brand"], Palette.version == doc["version"])
        )
        if exists is not None:
            continue
        pal = Palette(brand=doc["brand"], name=f'{doc["brand"]} {len(doc["colors"])}',
                      version=doc["version"])
        db.add(pal)
        db.flush()
        for c in doc["colors"]:
            rgb01 = [int(c["hex"][i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
            db.add(PaletteColor(
                palette_id=pal.id, code=c["code"], name=c.get("name", c["code"]),
                rgb=c["hex"], lab=[round(float(x), 4) for x in srgb_to_lab(rgb01)],
                in_sets=c.get("in_sets"), source=c["source"],
                confidence=c["confidence"], role=c.get("role"),
            ))
            written += 1
        db.flush()
    return written
