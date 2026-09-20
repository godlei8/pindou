import pytest

from app.models import User
from app.services import quota


def _user(db, q=2):
    u = User(username=f"u{q}{id(db) % 1000}", password_hash="x", ai_quota=q)
    db.add(u)
    db.flush()
    return u


def test_reserve_decrements_remaining(db):
    u = _user(db, q=3)
    assert quota.remaining(db, u.id) == 3
    quota.reserve(db, u.id)
    assert quota.remaining(db, u.id) == 2
    assert u.ai_used == 1


def test_reserve_raises_when_exhausted(db):
    u = _user(db, q=1)
    quota.reserve(db, u.id)
    with pytest.raises(quota.QuotaExceeded):
        quota.reserve(db, u.id)
    assert quota.remaining(db, u.id) == 0


def test_zero_quota_user_cannot_reserve(db):
    u = _user(db, q=0)
    with pytest.raises(quota.QuotaExceeded):
        quota.reserve(db, u.id)


def test_refund_restores_and_never_goes_negative(db):
    u = _user(db, q=2)
    quota.reserve(db, u.id)
    quota.refund(db, u.id)
    assert quota.remaining(db, u.id) == 2 and u.ai_used == 0
    quota.refund(db, u.id)
    assert u.ai_used == 0


def test_reserve_actually_locks_the_row(session_factory):
    """真并发：A 扣额度但不提交，B 再扣必须被行级锁挡住（用 lock_timeout 断言阻塞）。

    没有这把锁，两个并发请求会各自读到同一个 ai_used，把额度刷穿。
    """
    import pytest as _pytest
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    a, b = session_factory(), session_factory()
    try:
        u = User(username="lock-probe", password_hash="x", ai_quota=5)
        a.add(u)
        a.commit()

        quota.reserve(a, u.id)                       # A 持有行锁，未提交
        b.execute(text("SET LOCAL lock_timeout = '300ms'"))
        with _pytest.raises(OperationalError) as exc:
            quota.reserve(b, u.id)
        # 按 SQLSTATE 断言，不按消息文本——这台 PostgreSQL 是中文本地化的，
        # 错误消息会随 lc_messages 变，SQLSTATE 不会。55P03 = lock_not_available。
        assert exc.value.orig.sqlstate == "55P03"
    finally:
        a.rollback()
        b.rollback()
        c = session_factory()
        c.query(User).filter(User.username == "lock-probe").delete()
        c.commit()
        for s in (a, b, c):
            s.close()
