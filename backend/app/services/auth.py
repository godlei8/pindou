from __future__ import annotations

import uuid
from datetime import datetime, timezone

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import InviteCode, User

_ROUNDS = get_settings().bcrypt_rounds
_MIN_PASSWORD = 8
_SALT = "pindou-session"


class AuthError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt(rounds=_ROUNDS)).decode("ascii")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt=_SALT)


def make_session(user_id: uuid.UUID) -> str:
    return _serializer().dumps(str(user_id))


def read_session(token: str, max_age_seconds: int | None = None) -> uuid.UUID | None:
    if max_age_seconds is None:
        max_age_seconds = get_settings().session_max_age_days * 86400
    try:
        raw = _serializer().loads(token, max_age=max_age_seconds)
        return uuid.UUID(raw)
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None


def register(db: Session, username: str, password: str, invite_code: str) -> User:
    username = username.strip()
    if not username:
        raise AuthError("用户名不能为空")
    if len(password) < _MIN_PASSWORD:
        raise AuthError(f"密码至少 {_MIN_PASSWORD} 位")

    code = db.get(InviteCode, invite_code.strip(), with_for_update=True)
    if code is None or code.used_count >= code.max_uses:
        raise AuthError("邀请码无效或已用完")
    if code.expires_at is not None and code.expires_at < datetime.now(timezone.utc):
        raise AuthError("邀请码已过期")

    if db.scalar(select(User).where(User.username == username)) is not None:
        raise AuthError("用户名已被占用")

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    code.used_count += 1
    db.flush()
    return user


def authenticate(db: Session, username: str, password: str) -> User:
    user = db.scalar(select(User).where(User.username == username.strip()))
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("用户名或密码错误")
    if user.is_disabled:
        raise AuthError("账号已停用，请联系管理员")
    return user
