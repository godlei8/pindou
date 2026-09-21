from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    ai_quota: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    ai_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false",
                                           nullable=False)
    #: 管理员停用的账号：登录被拒，已有的登录态也立即失效（每次请求都查库）
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false",
                                              nullable=False)


class InviteCode(Base, TimestampMixin):
    __tablename__ = "invite_codes"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    max_uses: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
