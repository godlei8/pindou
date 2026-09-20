import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import InviteCode
from app.services import auth


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch):
    monkeypatch.setattr(auth, "_ROUNDS", 4)


def _code(db, code="LETMEIN", **kw):
    c = InviteCode(code=code, max_uses=kw.pop("max_uses", 2), **kw)
    db.add(c)
    db.flush()
    return c


def test_hash_and_verify():
    h = auth.hash_password("hunter2")
    assert h != "hunter2" and auth.verify_password("hunter2", h)
    assert not auth.verify_password("wrong", h)


def test_hash_is_salted():
    assert auth.hash_password("same") != auth.hash_password("same")


def test_register_consumes_invite_code(db):
    _code(db)
    u = auth.register(db, "alice", "pw12345678", "LETMEIN")
    assert u.username == "alice" and u.ai_quota >= 0
    assert db.get(InviteCode, "LETMEIN").used_count == 1


def test_register_rejects_unknown_code(db):
    with pytest.raises(auth.AuthError, match="邀请码"):
        auth.register(db, "bob", "pw12345678", "NOPE")


def test_register_rejects_exhausted_code(db):
    _code(db, max_uses=1)
    auth.register(db, "a", "pw12345678", "LETMEIN")
    with pytest.raises(auth.AuthError, match="邀请码"):
        auth.register(db, "b", "pw12345678", "LETMEIN")


def test_register_rejects_expired_code(db):
    _code(db, code="OLD", expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    with pytest.raises(auth.AuthError, match="邀请码"):
        auth.register(db, "c", "pw12345678", "OLD")


def test_register_rejects_duplicate_username(db):
    _code(db, max_uses=5)
    auth.register(db, "dup", "pw12345678", "LETMEIN")
    with pytest.raises(auth.AuthError, match="用户名"):
        auth.register(db, "dup", "pw12345678", "LETMEIN")


def test_register_rejects_short_password(db):
    _code(db)
    with pytest.raises(auth.AuthError, match="密码"):
        auth.register(db, "shorty", "123", "LETMEIN")


def test_authenticate_success_and_failure(db):
    _code(db)
    auth.register(db, "eve", "pw12345678", "LETMEIN")
    assert auth.authenticate(db, "eve", "pw12345678").username == "eve"
    with pytest.raises(auth.AuthError):
        auth.authenticate(db, "eve", "bad")
    with pytest.raises(auth.AuthError):
        auth.authenticate(db, "ghost", "pw12345678")


def test_session_roundtrip():
    uid = uuid.uuid4()
    assert auth.read_session(auth.make_session(uid)) == uid


def test_session_rejects_tampering():
    tok = auth.make_session(uuid.uuid4())
    assert auth.read_session(tok[:-3] + "xyz") is None
    assert auth.read_session("garbage") is None


def test_session_expires():
    # itsdangerous 的判定是 age > max_age，刚签发的 token age=0，
    # 所以 max_age=0 不算过期；用 -1 才能测到过期分支。
    tok = auth.make_session(uuid.uuid4())
    assert auth.read_session(tok, max_age_seconds=-1) is None
    assert auth.read_session(tok, max_age_seconds=3600) is not None
