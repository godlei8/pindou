from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk


class Palette(Base):
    __tablename__ = "palettes"

    id: Mapped[uuid.UUID] = uuid_pk()
    brand: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)


class PaletteColor(Base):
    __tablename__ = "palette_colors"
    __table_args__ = (UniqueConstraint("palette_id", "code", name="uq_palette_color_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    palette_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("palettes.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    rgb: Mapped[str] = mapped_column(String(7), nullable=False)
    lab: Mapped[list] = mapped_column(JSONB, nullable=False)
    in_sets: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(24), nullable=False)
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)
