from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_image_path: Mapped[str] = mapped_column(String(500), nullable=False)


class AiRender(Base, TimestampMixin):
    __tablename__ = "ai_renders"
    __table_args__ = (
        # NULLS NOT DISTINCT（PG 15+）：不加这个，style_preset_id 为 NULL 的行
        # 在 PostgreSQL 眼里互不相同，缓存键就形同虚设、同一张图会被反复重绘扣费。
        UniqueConstraint("project_id", "input_hash", "style_preset_id",
                         name="uq_ai_render_cache", postgresql_nulls_not_distinct=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    style_preset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("style_presets.id", ondelete="SET NULL"), nullable=True
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Pattern(Base, TimestampMixin):
    __tablename__ = "patterns"
    __table_args__ = (Index("ix_patterns_project_created", "project_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    ai_render_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_renders.id", ondelete="SET NULL"), nullable=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patterns.id", ondelete="SET NULL"), nullable=True
    )
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="generated")
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    grid: Mapped[list] = mapped_column(JSONB, nullable=False)
    color_stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    buildability: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    applied_patch: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    manual_edits: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    #: 出图时检测到的人脸（归一化坐标）。脸太小时提示调大格数；子版本沿用父版本的。
    faces: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    #: 还原度（core.fidelity）：{"score", "mean_delta_e", "worst_delta_e", "method"}。旧图纸为空
    fidelity: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)


class Feedback(Base, TimestampMixin):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = uuid_pk()
    pattern_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patterns.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    cells: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
