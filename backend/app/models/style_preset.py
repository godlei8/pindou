from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class StylePreset(Base, TimestampMixin):
    __tablename__ = "style_presets"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    #: 下拉里的排列次序，小的在前。默认选中的是第一个——而哪个该默认是有实测依据的
    #: （平涂方案图纸评分 87.4 > Q版盲盒 83.1），不该听凭名字的字母序。
    sort_order: Mapped[int] = mapped_column(Integer, default=100, server_default="100",
                                            nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true",
                                            nullable=False)
