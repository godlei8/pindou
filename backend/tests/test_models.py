import uuid

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.models import (AiRender, Feedback, InviteCode, Job, Palette, PaletteColor, Pattern,
                        Project, StylePreset, User)


def _user(db, name="alice"):
    u = User(username=name, password_hash="x", ai_quota=10)
    db.add(u)
    db.flush()
    return u


def test_user_username_is_unique(db):
    _user(db)
    db.add(User(username="alice", password_hash="y"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_user_quota_defaults(db):
    u = User(username="bob", password_hash="x")
    db.add(u)
    db.flush()
    assert u.ai_quota == 0 and u.ai_used == 0 and u.is_admin is False


def test_invite_code_roundtrip(db):
    db.add(InviteCode(code="LETMEIN", max_uses=3))
    db.flush()
    c = db.get(InviteCode, "LETMEIN")
    assert c.used_count == 0 and c.max_uses == 3


def test_project_pattern_version_tree(db):
    u = _user(db)
    p = Project(user_id=u.id, name="t", source_image_path="a.png")
    db.add(p)
    db.flush()
    root = Pattern(project_id=p.id, origin="generated", params={"grid_long_side": 48},
                   grid=[[0, 1], [1, 0]], color_stats={"0": 2, "1": 2})
    db.add(root)
    db.flush()
    child = Pattern(project_id=p.id, parent_id=root.id, origin="edited",
                    params=root.params, grid=[[0, 0], [1, 0]], color_stats={"0": 3, "1": 1},
                    manual_edits=[{"cell": [0, 1], "from": 1, "to": 0}])
    db.add(child)
    db.flush()
    assert child.parent_id == root.id
    assert db.get(Pattern, child.id).manual_edits[0]["to"] == 0


def test_jsonb_grid_survives_roundtrip(db):
    u = _user(db)
    p = Project(user_id=u.id, name="t", source_image_path="a.png")
    db.add(p)
    db.flush()
    grid = [[0, None, 2], [None, 1, 1]]
    pat = Pattern(project_id=p.id, origin="generated", params={}, grid=grid, color_stats={})
    db.add(pat)
    db.flush()
    db.expire(pat)
    assert db.get(Pattern, pat.id).grid == grid        # None 必须原样保留，不能变成 0


def test_ai_render_cache_key_is_unique(db):
    u = _user(db)
    p = Project(user_id=u.id, name="t", source_image_path="a.png")
    db.add(p)
    db.flush()
    for _ in range(2):
        db.add(AiRender(project_id=p.id, provider="fake", model="m", prompt="p",
                        params={}, input_hash="h1", status="done"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_palette_color_unique_per_palette(db):
    pal = Palette(brand="MARD", name="MARD 291", version="2026-09-20")
    db.add(pal)
    db.flush()
    db.add(PaletteColor(palette_id=pal.id, code="A1", name="A1", rgb="#F9F0CD",
                        lab=[94.7, -2.6, 18.0], source="beadcolors", confidence="agree"))
    db.flush()
    db.add(PaletteColor(palette_id=pal.id, code="A1", name="dup", rgb="#000000",
                        lab=[0, 0, 0], source="x", confidence="x"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_feedback_records_cells(db):
    u = _user(db)
    p = Project(user_id=u.id, name="t", source_image_path="a.png")
    db.add(p)
    db.flush()
    pat = Pattern(project_id=p.id, origin="generated", params={}, grid=[[0]], color_stats={})
    db.add(pat)
    db.flush()
    db.add(Feedback(pattern_id=pat.id, user_id=u.id, kind="断裂",
                    cells=[[34, 17], [34, 18]], note="发尾断了"))
    db.flush()
    fb = db.scalars(select(Feedback)).one()
    assert fb.cells == [[34, 17], [34, 18]] and fb.kind == "断裂"


def test_job_defaults_and_index(db, test_engine):
    j = Job(type="generate", payload={"project_id": str(uuid.uuid4())})
    db.add(j)
    db.flush()
    assert j.status == "pending" and j.attempts == 0 and j.locked_at is None
    idx = {i["name"] for i in inspect(test_engine).get_indexes("jobs")}
    assert any("status" in n for n in idx)


def test_style_preset_versioning(db):
    db.add(StylePreset(name="Q版盲盒", prompt="粗轮廓 纯色平涂 无渐变", params={"scale": 0.5}))
    db.flush()
    sp = db.scalars(select(StylePreset)).one()
    assert sp.version == 1 and sp.is_active is True
