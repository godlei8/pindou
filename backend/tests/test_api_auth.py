import pytest

from app.models import InviteCode
from app.services import auth


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch):
    monkeypatch.setattr(auth, "_ROUNDS", 4)


@pytest.fixture
def invite(db):
    c = InviteCode(code="OPEN2026", max_uses=5)
    db.add(c)
    db.flush()
    return c


def test_register_then_me(client, invite):
    r = client.post("/api/auth/register",
                    json={"username": "amy", "password": "pw12345678",
                          "invite_code": "OPEN2026"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["username"] == "amy" and body["ai_used"] == 0
    assert "password" not in body and "password_hash" not in body

    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["username"] == "amy"


def test_register_sets_httponly_cookie(client, invite):
    r = client.post("/api/auth/register",
                    json={"username": "cookie", "password": "pw12345678",
                          "invite_code": "OPEN2026"})
    set_cookie = r.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


def test_register_rejects_bad_invite(client):
    r = client.post("/api/auth/register",
                    json={"username": "x", "password": "pw12345678", "invite_code": "NOPE"})
    assert r.status_code == 400 and "邀请码" in r.json()["detail"]


def test_register_rejects_short_password(client, invite):
    r = client.post("/api/auth/register",
                    json={"username": "x", "password": "123", "invite_code": "OPEN2026"})
    assert r.status_code == 400


def test_login_logout_cycle(client, invite):
    client.post("/api/auth/register",
                json={"username": "leo", "password": "pw12345678", "invite_code": "OPEN2026"})
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    bad = client.post("/api/auth/login", json={"username": "leo", "password": "wrong"})
    assert bad.status_code == 401

    ok = client.post("/api/auth/login", json={"username": "leo", "password": "pw12345678"})
    assert ok.status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "leo"


def test_me_without_cookie_is_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_tampered_cookie_is_401(client, invite):
    client.post("/api/auth/register",
                json={"username": "tam", "password": "pw12345678", "invite_code": "OPEN2026"})
    client.cookies.set("pindou_session", "forged.value.here")
    assert client.get("/api/auth/me").status_code == 401


def test_health_needs_no_auth(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
