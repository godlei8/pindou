from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


class QuotaExceeded(Exception):
    pass


def _locked_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise LookupError(f"user {user_id} not found")
    return user


def reserve(db: Session, user_id: uuid.UUID) -> None:
    """先扣后跑。行级锁保证并发提交不会把额度刷穿。"""
    user = _locked_user(db, user_id)
    if user.ai_used + 1 > user.ai_quota:
        raise QuotaExceeded(f"AI 额度不足：已用 {user.ai_used} / 共 {user.ai_quota}")
    user.ai_used += 1
    db.flush()


def refund(db: Session, user_id: uuid.UUID) -> None:
    user = _locked_user(db, user_id)
    user.ai_used = max(0, user.ai_used - 1)
    db.flush()


def remaining(db: Session, user_id: uuid.UUID) -> int:
    user = db.get(User, user_id)
    if user is None:
        raise LookupError(f"user {user_id} not found")
    return max(0, user.ai_quota - user.ai_used)
