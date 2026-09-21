"""管理后台：只给管理员用。

五块：实拼反馈、AI 用量和花费、邀请码、用户和额度、风格预设。
原来这些都只能在命令行（python -m app.cli）或直接查库做。
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import current_admin
from app.db import get_db
from app.models import AiRender, Feedback, InviteCode, Pattern, Project, StylePreset, User
from app.services import patterns as psvc
from app.services.palettes import load_core_palette

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(current_admin)])


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- 实拼反馈 ----------

@router.get("/feedback")
def list_feedback(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Feedback, User.username, Project.id, Project.name)
        .join(User, User.id == Feedback.user_id)
        .join(Pattern, Pattern.id == Feedback.pattern_id)
        .join(Project, Project.id == Pattern.project_id)
        .order_by(Feedback.created_at.desc()).limit(limit)).all()
    return [{"id": fb.id, "kind": fb.kind, "note": fb.note, "cells": len(fb.cells or []),
             "created_at": fb.created_at, "username": username,
             "project_id": pid, "project_name": pname, "pattern_id": fb.pattern_id}
            for fb, username, pid, pname in rows]


@router.get("/patterns/{pattern_id}/thumb")
def pattern_thumb(pattern_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    """看反馈时要看到是哪张图纸——普通的缩略图接口只给图纸主人看。"""
    pat = db.get(Pattern, pattern_id)
    if pat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "图纸不存在")
    palette = load_core_palette((pat.params or {}).get("palette_id", "mard"))
    return Response(psvc.thumb_png(pat, palette), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=31536000, immutable"})


# ---------- AI 用量和花费 ----------

@router.get("/ai-usage")
def ai_usage(recent: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)) -> dict:
    done = func.sum(case((AiRender.status == "done", 1), else_=0))
    failed = func.sum(case((AiRender.status == "failed", 1), else_=0))
    cost = func.coalesce(func.sum(AiRender.cost), 0)
    per_user = db.execute(
        select(User.username, User.ai_quota, User.ai_used, func.count(AiRender.id),
               done, failed, cost)
        .join(Project, Project.user_id == User.id)
        .join(AiRender, AiRender.project_id == Project.id)
        .group_by(User.id).order_by(func.count(AiRender.id).desc())).all()
    users = [{"username": u, "ai_quota": q, "ai_used": used, "renders": n,
              "done": int(d or 0), "failed": int(f or 0), "cost": str(Decimal(c))}
             for u, q, used, n, d, f, c in per_user]

    rows = db.execute(
        select(AiRender, User.username, Project.name, StylePreset.name)
        .join(Project, Project.id == AiRender.project_id)
        .join(User, User.id == Project.user_id)
        .outerjoin(StylePreset, StylePreset.id == AiRender.style_preset_id)
        .order_by(AiRender.created_at.desc()).limit(recent)).all()
    items = [{"id": r.id, "created_at": r.created_at, "username": username,
              "project_name": pname, "preset": preset, "provider": r.provider, "model": r.model,
              "status": r.status, "cost": None if r.cost is None else str(r.cost),
              "error": r.error}
             for r, username, pname, preset in rows]

    return {"total": {"renders": sum(u["renders"] for u in users),
                      "done": sum(u["done"] for u in users),
                      "failed": sum(u["failed"] for u in users),
                      "cost": str(sum((Decimal(u["cost"]) for u in users), Decimal(0)))},
            "users": users, "recent": items}


# ---------- 邀请码 ----------

def _invite_out(c: InviteCode, now: datetime) -> dict:
    if c.expires_at is not None and c.expires_at <= now:
        state = "expired"
    elif c.used_count >= c.max_uses:
        state = "used_up"
    else:
        state = "active"
    return {"code": c.code, "max_uses": c.max_uses, "used_count": c.used_count,
            "expires_at": c.expires_at, "created_at": c.created_at, "state": state}


class InviteIn(BaseModel):
    count: int = Field(1, ge=1, le=20)
    max_uses: int = Field(1, ge=1, le=1000)
    #: 几天后过期；不填就永不过期
    expires_days: int | None = Field(None, ge=1, le=365)


def _new_code() -> str:
    # 和 CLI 一样：12 位大写字母数字，去掉 - _ 这种念出来容易错的字符
    return secrets.token_urlsafe(9).replace("-", "X").replace("_", "Y")[:12].upper()


@router.get("/invites")
def list_invites(db: Session = Depends(get_db)) -> list[dict]:
    now = _now()
    return [_invite_out(c, now) for c in
            db.scalars(select(InviteCode).order_by(InviteCode.created_at.desc())).all()]


@router.post("/invites", status_code=status.HTTP_201_CREATED)
def create_invites(body: InviteIn, admin: User = Depends(current_admin),
                   db: Session = Depends(get_db)) -> list[dict]:
    expires = _now() + timedelta(days=body.expires_days) if body.expires_days else None
    codes = []
    for _ in range(body.count):
        c = InviteCode(code=_new_code(), created_by=admin.id, max_uses=body.max_uses,
                       expires_at=expires)
        db.add(c)
        codes.append(c)
    db.commit()
    now = _now()
    return [_invite_out(c, now) for c in codes]


@router.post("/invites/{code}/revoke")
def revoke_invite(code: str, db: Session = Depends(get_db)) -> dict:
    """作废 = 让它立刻过期。不删记录：已经用它注册的人还要能查到来源。"""
    c = db.get(InviteCode, code)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "邀请码不存在")
    now = _now()
    if c.expires_at is None or c.expires_at > now:
        c.expires_at = now
    db.commit()
    return _invite_out(c, _now())


# ---------- 用户和额度 ----------

def _user_out(u: User, projects: int) -> dict:
    return {"id": u.id, "username": u.username, "ai_quota": u.ai_quota, "ai_used": u.ai_used,
            "is_admin": u.is_admin, "is_disabled": u.is_disabled, "created_at": u.created_at,
            "projects": projects}


@router.get("/users")
def list_users(db: Session = Depends(get_db)) -> list[dict]:
    n = (select(Project.user_id, func.count(Project.id).label("n"))
         .group_by(Project.user_id).subquery())
    rows = db.execute(select(User, func.coalesce(n.c.n, 0))
                      .outerjoin(n, n.c.user_id == User.id)
                      .order_by(User.created_at)).all()
    return [_user_out(u, p) for u, p in rows]


class UserPatch(BaseModel):
    #: 额度增减（正数加、负数减）。总额度不能低于已用次数。
    quota_delta: int | None = Field(None, ge=-10000, le=10000)
    is_disabled: bool | None = None
    is_admin: bool | None = None


@router.patch("/users/{user_id}")
def patch_user(user_id: uuid.UUID, body: UserPatch, admin: User = Depends(current_admin),
               db: Session = Depends(get_db)) -> dict:
    u = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    if u.id == admin.id and (body.is_disabled or body.is_admin is False):
        # 把自己停用或撤掉管理员，后台就再也进不来了
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能停用自己或撤销自己的管理员")
    if body.quota_delta:
        new = u.ai_quota + body.quota_delta
        if new < u.ai_used:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"总额度不能低于已用次数（已用 {u.ai_used}）")
        u.ai_quota = new
    if body.is_disabled is not None:
        u.is_disabled = body.is_disabled
    if body.is_admin is not None:
        u.is_admin = body.is_admin
    db.commit()
    projects = db.scalar(select(func.count(Project.id)).where(Project.user_id == u.id)) or 0
    return _user_out(u, projects)


# ---------- 风格预设 ----------

def _preset_out(p: StylePreset) -> dict:
    return {"id": p.id, "name": p.name, "prompt": p.prompt, "params": p.params or {},
            "version": p.version, "sort_order": p.sort_order, "is_active": p.is_active}


class PresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=4000)
    sort_order: int = Field(100, ge=0, le=10000)
    is_active: bool = True


class PresetPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    prompt: str | None = Field(None, min_length=1, max_length=4000)
    sort_order: int | None = Field(None, ge=0, le=10000)
    is_active: bool | None = None


@router.get("/presets")
def list_presets(db: Session = Depends(get_db)) -> list[dict]:
    """包括已停用的——前台只列启用的。"""
    return [_preset_out(p) for p in db.scalars(
        select(StylePreset).order_by(StylePreset.sort_order, StylePreset.name)).all()]


@router.post("/presets", status_code=status.HTTP_201_CREATED)
def create_preset(body: PresetIn, db: Session = Depends(get_db)) -> dict:
    p = StylePreset(name=body.name.strip(), prompt=body.prompt.strip(), params={},
                    sort_order=body.sort_order, is_active=body.is_active)
    db.add(p)
    db.commit()
    return _preset_out(p)


@router.patch("/presets/{preset_id}")
def patch_preset(preset_id: uuid.UUID, body: PresetPatch, db: Session = Depends(get_db)) -> dict:
    p = db.get(StylePreset, preset_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "风格预设不存在")
    if body.name is not None:
        p.name = body.name.strip()
    if body.prompt is not None and body.prompt.strip() != p.prompt:
        # 改提示词 = 新版本。AI 重绘的缓存按"原图 + 提示词 + 参数"算哈希，
        # 提示词一变哈希就变，不会把旧提示词画的图当成新提示词的结果复用。
        p.prompt = body.prompt.strip()
        p.version += 1
    if body.sort_order is not None:
        p.sort_order = body.sort_order
    if body.is_active is not None:
        p.is_active = body.is_active
    db.commit()
    return _preset_out(p)
