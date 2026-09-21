"""管理后台接口。"""
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import AiRender, Feedback, InviteCode, Project, StylePreset, User

LOGO = (Path(__file__).parent / "fixtures" / "images" / "logo.png").read_bytes()


@pytest.fixture
def admin_client(auth_client, db):
    auth_client.user.is_admin = True
    db.flush()
    return auth_client


def _other_user(db, name="someone", **kw):
    u = User(username=name, password_hash="x", **kw)
    db.add(u)
    db.flush()
    return u


# ---- 门禁 ----------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/admin/feedback", "/api/admin/ai-usage",
                                  "/api/admin/invites", "/api/admin/users",
                                  "/api/admin/presets"])
def test_non_admin_is_refused(auth_client, path):
    assert auth_client.get(path).status_code == 403


def test_anonymous_is_refused(client):
    assert client.get("/api/admin/users").status_code == 401


# ---- 停用账号 --------------------------------------------------------------------

def test_disabled_user_cannot_log_in(admin_client, db):
    admin_client.post("/api/auth/logout")
    admin_client.user.is_disabled = True
    db.flush()
    r = admin_client.post("/api/auth/login",
                          json={"username": "fixture-user", "password": "pw12345678"})
    assert r.status_code == 400 and "停用" in r.json()["detail"]


def test_disabling_kills_an_existing_session(auth_client, db):
    """已登录的人被停用后，下一个请求就被拒，不用等会话过期。"""
    assert auth_client.get("/api/auth/me").status_code == 200
    auth_client.user.is_disabled = True
    db.flush()
    assert auth_client.get("/api/auth/me").status_code == 401


# ---- 用户和额度 -------------------------------------------------------------------

def test_list_users_with_project_counts(admin_client, db):
    admin_client.post("/api/projects", data={"name": "p"},
                      files={"file": ("a.png", LOGO, "image/png")})
    users = {u["username"]: u for u in admin_client.get("/api/admin/users").json()}
    assert users["fixture-user"]["projects"] == 1
    assert users["fixture-user"]["is_admin"] is True


def test_add_and_subtract_quota(admin_client, db):
    u = _other_user(db, ai_quota=5, ai_used=3)
    r = admin_client.patch(f"/api/admin/users/{u.id}", json={"quota_delta": 10})
    assert r.status_code == 200 and r.json()["ai_quota"] == 15
    r = admin_client.patch(f"/api/admin/users/{u.id}", json={"quota_delta": -12})
    assert r.json()["ai_quota"] == 3


def test_quota_cannot_go_below_used(admin_client, db):
    u = _other_user(db, ai_quota=5, ai_used=3)
    r = admin_client.patch(f"/api/admin/users/{u.id}", json={"quota_delta": -3})
    assert r.status_code == 400
    db.refresh(u)
    assert u.ai_quota == 5


def test_disable_and_promote_someone_else(admin_client, db):
    u = _other_user(db)
    r = admin_client.patch(f"/api/admin/users/{u.id}", json={"is_disabled": True, "is_admin": True})
    assert r.json()["is_disabled"] is True and r.json()["is_admin"] is True


@pytest.mark.parametrize("body", [{"is_disabled": True}, {"is_admin": False}])
def test_admin_cannot_lock_themselves_out(admin_client, db, body):
    r = admin_client.patch(f"/api/admin/users/{admin_client.user.id}", json=body)
    assert r.status_code == 400
    db.refresh(admin_client.user)
    assert admin_client.user.is_admin and not admin_client.user.is_disabled


# ---- 邀请码 ---------------------------------------------------------------------

def test_generate_invites(admin_client, db):
    r = admin_client.post("/api/admin/invites", json={"count": 3, "max_uses": 2, "expires_days": 7})
    assert r.status_code == 201
    codes = r.json()
    assert len(codes) == 3 and len({c["code"] for c in codes}) == 3
    assert all(c["state"] == "active" and c["max_uses"] == 2 and c["expires_at"] for c in codes)
    row = db.get(InviteCode, codes[0]["code"])
    assert row.created_by == admin_client.user.id


def test_invite_states(admin_client, db):
    db.add(InviteCode(code="FULL", max_uses=1, used_count=1))
    db.flush()
    states = {c["code"]: c["state"] for c in admin_client.get("/api/admin/invites").json()}
    assert states["FULL"] == "used_up"
    assert states["FIXTURE"] == "active"


def test_revoked_invite_can_no_longer_register(admin_client, db):
    code = admin_client.post("/api/admin/invites", json={}).json()[0]["code"]
    r = admin_client.post(f"/api/admin/invites/{code}/revoke")
    assert r.json()["state"] == "expired"
    admin_client.post("/api/auth/logout")
    r = admin_client.post("/api/auth/register",
                          json={"username": "late", "password": "pw12345678", "invite_code": code})
    assert r.status_code == 400


# ---- 风格预设 --------------------------------------------------------------------

def test_presets_include_inactive_ones(admin_client, db):
    db.add(StylePreset(name="旧风格", prompt="p", params={}, is_active=False))
    db.flush()
    names = [p["name"] for p in admin_client.get("/api/admin/presets").json()]
    assert "旧风格" in names
    # 前台照旧只看得到启用的
    assert "旧风格" not in [p["name"] for p in admin_client.get("/api/style-presets").json()]


def test_create_and_edit_preset(admin_client):
    p = admin_client.post("/api/admin/presets",
                          json={"name": "像素", "prompt": "draw pixel", "sort_order": 5}).json()
    assert p["version"] == 1 and p["is_active"] is True
    r = admin_client.patch(f"/api/admin/presets/{p['id']}", json={"name": "像素风"})
    assert r.json()["version"] == 1, "只改名字不算新版本"
    r = admin_client.patch(f"/api/admin/presets/{p['id']}", json={"prompt": "draw pixel art"})
    assert r.json()["version"] == 2 and r.json()["prompt"] == "draw pixel art"
    r = admin_client.patch(f"/api/admin/presets/{p['id']}", json={"is_active": False})
    assert r.json()["is_active"] is False


def test_changing_the_prompt_does_not_reuse_old_ai_renders(admin_client, db):
    """缓存键里有提示词：改了提示词，同一张图要重新画，不能拿旧提示词的结果充数。"""
    from app.services import renders
    pid = admin_client.post("/api/projects", data={"name": "p"},
                            files={"file": ("a.png", LOGO, "image/png")}).json()["id"]
    preset = StylePreset(name="s", prompt="old", params={})
    db.add(preset)
    db.flush()
    proj = db.get(Project, pid)
    first = renders.redraw(db, admin_client.user.id, proj, preset)
    admin_client.patch(f"/api/admin/presets/{preset.id}", json={"prompt": "new"})
    db.refresh(preset)
    second = renders.redraw(db, admin_client.user.id, proj, preset)
    assert second.id != first.id


# ---- AI 用量 --------------------------------------------------------------------

def test_ai_usage_totals(admin_client, db):
    pid = admin_client.post("/api/projects", data={"name": "p"},
                            files={"file": ("a.png", LOGO, "image/png")}).json()["id"]
    for i, (status, cost, err) in enumerate((("done", Decimal("0.2"), None), ("done", Decimal("0.2"), None),
                              ("failed", None, "超时"))):
        db.add(AiRender(project_id=pid, provider="fake", model="m", prompt="p", params={},
                        input_hash=f"h{i}", status=status, cost=cost, error=err))
    db.flush()
    data = admin_client.get("/api/admin/ai-usage").json()
    assert data["total"] == {"renders": 3, "done": 2, "failed": 1, "cost": "0.4000"}
    me = data["users"][0]
    assert me["username"] == "fixture-user" and me["failed"] == 1
    assert len(data["recent"]) == 3
    assert any(r["error"] == "超时" for r in data["recent"])


# ---- 实拼反馈 --------------------------------------------------------------------

def test_feedback_list_and_thumb(admin_client, db):
    pid = admin_client.post("/api/projects", data={"name": "草莓"},
                            files={"file": ("a.png", LOGO, "image/png")}).json()["id"]
    pat = admin_client.post(f"/api/projects/{pid}/patterns", json={"params": {}}).json()
    db.add(Feedback(pattern_id=pat["id"], user_id=admin_client.user.id, kind="hard_to_build",
                    cells=[[0, 0], [1, 1]], note="这块太碎"))
    db.flush()
    items = admin_client.get("/api/admin/feedback").json()
    assert items[0]["note"] == "这块太碎" and items[0]["cells"] == 2
    assert items[0]["project_name"] == "草莓" and items[0]["username"] == "fixture-user"

    r = admin_client.get(f"/api/admin/patterns/{pat['id']}/thumb")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_admin_can_see_other_peoples_thumbs(admin_client, db):
    """普通缩略图接口只给主人看；后台接口不受这个限制。"""
    other = _other_user(db)
    db.add(Project(user_id=other.id, name="x", source_image_path="nope"))
    db.flush()
    proj = db.scalar(select(Project).where(Project.user_id == other.id))
    from app.models import Pattern
    pat = Pattern(project_id=proj.id, params={}, grid=[[0, 0], [0, 0]], color_stats={})
    db.add(pat)
    db.flush()
    assert admin_client.get(f"/api/patterns/{pat.id}/thumb").status_code == 404
    assert admin_client.get(f"/api/admin/patterns/{pat.id}/thumb").status_code == 200


# ---- 管理员独立登录 ----------------------------------------------------------------

def _login_admin(client, username="fixture-user", password="pw12345678"):
    return client.post("/api/auth/admin-login", json={"username": username, "password": password})


def test_admin_login_lets_admins_in(admin_client):
    admin_client.post("/api/auth/logout")
    r = _login_admin(admin_client)
    assert r.status_code == 200 and r.json()["is_admin"] is True
    assert admin_client.get("/api/admin/users").status_code == 200


def test_admin_login_refuses_plain_users_without_a_session(auth_client):
    auth_client.post("/api/auth/logout")
    r = _login_admin(auth_client)
    assert r.status_code == 403 and "不是管理员" in r.json()["detail"]
    assert "set-cookie" not in r.headers
    assert auth_client.get("/api/auth/me").status_code == 401


def test_admin_login_wrong_password_is_401(admin_client):
    admin_client.post("/api/auth/logout")
    assert _login_admin(admin_client, password="wrong-password").status_code == 401


def test_disabled_admin_cannot_use_admin_login(admin_client, db):
    admin_client.post("/api/auth/logout")
    admin_client.user.is_disabled = True
    db.flush()
    assert _login_admin(admin_client).status_code == 400
