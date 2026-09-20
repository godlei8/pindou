from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------

class RegisterIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    invite_code: str = Field(min_length=1, max_length=64)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(_Base):
    id: uuid.UUID
    username: str
    ai_quota: int
    ai_used: int
    is_admin: bool


# ---------- projects & patterns ----------

class PatternBrief(_Base):
    id: uuid.UUID
    origin: str
    parent_id: uuid.UUID | None
    created_at: datetime
    score: float | None = None
    n_colors: int = 0


class ProjectOut(_Base):
    id: uuid.UUID
    name: str
    created_at: datetime
    patterns: list[PatternBrief] = []


class GenerateIn(BaseModel):
    use_ai: bool = False
    style_preset_id: uuid.UUID | None = None
    provider: str | None = None
    params: dict = Field(default_factory=dict)


class PatternParamsIn(BaseModel):
    source: str = "original"
    ai_render_id: uuid.UUID | None = None
    params: dict = Field(default_factory=dict)


class PatternOut(_Base):
    id: uuid.UUID
    project_id: uuid.UUID
    parent_id: uuid.UUID | None
    origin: str
    params: dict
    grid: list
    color_stats: dict
    buildability: dict | None
    materials: list[dict] = []
    palette_id: str = "mard"
    created_at: datetime


class EditCell(BaseModel):
    cell: list[int] = Field(min_length=2, max_length=2)
    to: int | None = None


class EditIn(BaseModel):
    edits: list[EditCell] = Field(min_length=1, max_length=20000)
    protected_cells: list[list[int]] | None = None


class PatchIn(BaseModel):
    issue_index: int = Field(ge=0)


class FeedbackIn(BaseModel):
    kind: str = Field(min_length=1, max_length=32)
    cells: list[list[int]] = Field(default_factory=list, max_length=20000)
    note: str | None = Field(default=None, max_length=2000)


# ---------- jobs & meta ----------

class JobOut(_Base):
    id: int
    type: str
    status: str
    result: dict | None
    error: str | None
    created_at: datetime


class PaletteOut(_Base):
    id: uuid.UUID
    brand: str
    name: str
    version: str


class PaletteColorOut(BaseModel):
    index: int
    code: str
    name: str
    hex: str
    role: str | None = None
    confidence: str


class StylePresetOut(_Base):
    id: uuid.UUID
    name: str
    prompt: str
    version: int


class SizeSuggestion(BaseModel):
    long_side: int
    detail_loss: float
