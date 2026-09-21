import io
import uuid
from pathlib import Path

from PIL import Image

from app.models import AiRender, Project, StylePreset

FIXTURES = Path(__file__).parent / "fixtures" / "images"


def _upload(client, name="t", path="logo.png"):
    return client.post("/api/projects", data={"name": name},
                       files={"file": (path, (FIXTURES / path).read_bytes(), "image/png")})


def test_create_and_list_project(auth_client):
    r = _upload(auth_client, "我的第一张")
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["name"] == "我的第一张"

    lst = auth_client.get("/api/projects")
    assert lst.status_code == 200 and [p["id"] for p in lst.json()] == [pid]


def test_create_rejects_non_image(auth_client):
    r = auth_client.post("/api/projects", data={"name": "bad"},
                         files={"file": ("x.png", b"definitely not a png", "image/png")})
    assert r.status_code == 400 and "格式" in r.json()["detail"]


def test_project_requires_auth(client):
    assert client.get("/api/projects").status_code == 401


def test_cannot_read_other_users_project(auth_client, client, invite_other):
    pid = _upload(auth_client).json()["id"]
    client.cookies.clear()
    client.post("/api/auth/register",
                json={"username": "intruder", "password": "pw12345678",
                      "invite_code": "OTHER"})
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_source_image_is_served_back(auth_client):
    pid = _upload(auth_client).json()["id"]
    r = auth_client.get(f"/api/projects/{pid}/source")
    assert r.status_code == 200
    assert Image.open(io.BytesIO(r.content)).size[0] > 0


def test_suggest_sizes(auth_client):
    pid = _upload(auth_client).json()["id"]
    r = auth_client.get(f"/api/projects/{pid}/suggest-sizes?base=40")
    assert r.status_code == 200
    body = r.json()
    assert [x["long_side"] for x in body] == [30, 40, 60]
    assert body[0]["detail_loss"] >= body[-1]["detail_loss"]


def test_generate_without_ai_enqueues_job(auth_client):
    pid = _upload(auth_client).json()["id"]
    r = auth_client.post(f"/api/projects/{pid}/generate",
                         json={"use_ai": False,
                               "params": {"grid_long_side": 20, "max_colors": 4}})
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    got = auth_client.get(f"/api/jobs/{job_id}")
    assert got.status_code == 200
    assert got.json()["status"] in {"pending", "running", "done", "failed"}


def test_generate_rejects_bad_params_before_enqueue(auth_client):
    pid = _upload(auth_client).json()["id"]
    r = auth_client.post(f"/api/projects/{pid}/generate",
                         json={"use_ai": False, "params": {"grid_long_side": 99999}})
    assert r.status_code == 400


def test_generate_with_ai_but_no_preset_is_rejected(auth_client):
    pid = _upload(auth_client).json()["id"]
    r = auth_client.post(f"/api/projects/{pid}/generate", json={"use_ai": True})
    assert r.status_code == 400


def test_generate_with_ai_without_quota_is_402(auth_client, db):
    auth_client.user.ai_quota = 0
    db.flush()
    sp = StylePreset(name="Q版", prompt="粗轮廓", params={})
    db.add(sp)
    db.flush()
    pid = _upload(auth_client).json()["id"]
    r = auth_client.post(f"/api/projects/{pid}/generate",
                         json={"use_ai": True, "style_preset_id": str(sp.id)})
    assert r.status_code == 402


def test_job_of_another_user_is_404(auth_client, client, invite_other):
    pid = _upload(auth_client).json()["id"]
    job_id = auth_client.post(f"/api/projects/{pid}/generate",
                              json={"use_ai": False,
                                    "params": {"grid_long_side": 16}}).json()["id"]
    client.cookies.clear()
    client.post("/api/auth/register",
                json={"username": "nosy", "password": "pw12345678", "invite_code": "OTHER"})
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def _make_render(db, project_id, *, output_path, status="done"):
    """直接塞一条 AiRender。走真实 provider 会花钱，这里只测取图端点本身。"""
    render = AiRender(project_id=uuid.UUID(project_id), provider="fake", model="fake-v1",
                      style_preset_id=None, prompt="p", params={},
                      input_hash="h" * 64, output_path=output_path, status=status)
    db.add(render)
    db.commit()
    return str(render.id)


def test_ai_render_image_is_served_back(auth_client, db):
    pid = _upload(auth_client).json()["id"]
    # 复用项目自己的原图当"AI 成品"——端点只负责按路径取字节
    proj = db.get(Project, uuid.UUID(pid))
    rid = _make_render(db, pid, output_path=proj.source_image_path)

    r = auth_client.get(f"/api/projects/{pid}/ai-renders/{rid}/image")
    assert r.status_code == 200, r.text
    assert Image.open(io.BytesIO(r.content)).size[0] > 0


def test_ai_render_still_pending_says_so(auth_client, db):
    pid = _upload(auth_client).json()["id"]
    rid = _make_render(db, pid, output_path=None, status="running")
    r = auth_client.get(f"/api/projects/{pid}/ai-renders/{rid}/image")
    assert r.status_code == 404 and "running" in r.json()["detail"]


def test_ai_render_of_another_project_is_not_reachable(auth_client, db):
    """AiRender 没有 user_id，归属只能经 project 认。跨项目取图必须挡住。"""
    mine = _upload(auth_client, "我的").json()["id"]
    other = _upload(auth_client, "另一个").json()["id"]
    proj = db.get(Project, uuid.UUID(other))
    rid = _make_render(db, other, output_path=proj.source_image_path)

    assert auth_client.get(f"/api/projects/{mine}/ai-renders/{rid}/image").status_code == 404


def test_ai_render_requires_owning_the_project(auth_client, client, invite_other, db):
    pid = _upload(auth_client).json()["id"]
    proj = db.get(Project, uuid.UUID(pid))
    rid = _make_render(db, pid, output_path=proj.source_image_path)

    client.cookies.clear()
    client.post("/api/auth/register",
                json={"username": "intruder2", "password": "pw12345678",
                      "invite_code": "OTHER"})
    assert client.get(f"/api/projects/{pid}/ai-renders/{rid}/image").status_code == 404


def test_brief_marks_which_versions_came_from_ai(auth_client, db):
    """版本列表靠 ai_render_id 区分来源——origin 对两种来源都是 generated。"""
    pid = _upload(auth_client).json()["id"]
    auth_client.post(f"/api/projects/{pid}/patterns",
                     json={"source": "original", "params": {"grid_long_side": 16}})

    briefs = auth_client.get(f"/api/projects/{pid}").json()["patterns"]
    assert briefs and all(b["ai_render_id"] is None for b in briefs)
    assert {b["origin"] for b in briefs} == {"generated"}
