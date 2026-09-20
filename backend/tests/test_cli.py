import pytest
from sqlalchemy import func, select

from app import cli
from app.models import InviteCode, PaletteColor, StylePreset, User


def test_invite_creates_codes(db):
    n = cli.cmd_invite(db, count=3, uses=2)
    assert n == 3
    codes = db.scalars(select(InviteCode)).all()
    assert len(codes) == 3 and all(c.max_uses == 2 for c in codes)
    assert all(len(c.code) >= 8 for c in codes)
    assert len({c.code for c in codes}) == 3


def test_quota_add_and_report(db):
    u = User(username="q", password_hash="x", ai_quota=1)
    db.add(u)
    db.flush()
    left = cli.cmd_quota(db, username="q", add=9)
    assert left == 10 and u.ai_quota == 10


def test_quota_unknown_user_raises(db):
    with pytest.raises(SystemExit):
        cli.cmd_quota(db, username="ghost", add=1)


def test_seed_palettes_command(db):
    n = cli.cmd_seed_palettes(db)
    assert n >= 291
    assert db.scalar(select(func.count()).select_from(PaletteColor)) == n


def test_preset_command(db):
    sp = cli.cmd_preset(db, name="Q版盲盒", prompt="粗轮廓 纯色平涂 无渐变")
    assert isinstance(sp, StylePreset) and sp.is_active is True


def test_admin_command(db):
    u = User(username="boss", password_hash="x")
    db.add(u)
    db.flush()
    cli.cmd_admin(db, username="boss")
    assert u.is_admin is True
