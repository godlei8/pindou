from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "images"


def _project(auth_client, path="logo.png"):
    return auth_client.post("/api/projects", data={"name": "t"},
                            files={"file": (path, (FIXTURES / path).read_bytes(),
                                            "image/png")}).json()["id"]


@pytest.fixture
def pattern(auth_client):
    pid = _project(auth_client)
    r = auth_client.post(f"/api/projects/{pid}/patterns",
                         json={"params": {"grid_long_side": 20, "max_colors": 5}})
    assert r.status_code == 200, r.text
    return r.json()


def test_sync_recompute_returns_full_pattern(pattern):
    assert len(pattern["grid"]) == 20
    assert pattern["origin"] == "generated"
    assert pattern["buildability"]["score"] >= 0
    assert pattern["materials"] and "code" in pattern["materials"][0]


def test_changing_params_changes_grid(auth_client, pattern):
    pid = pattern["project_id"]
    other = auth_client.post(f"/api/projects/{pid}/patterns",
                             json={"params": {"grid_long_side": 30, "max_colors": 5}}).json()
    assert len(other["grid"]) == 30 and other["id"] != pattern["id"]


def test_get_pattern_by_id(auth_client, pattern):
    r = auth_client.get(f"/api/patterns/{pattern['id']}")
    assert r.status_code == 200 and r.json()["id"] == pattern["id"]


def test_apply_patch_creates_child(auth_client):
    pid = _project(auth_client, "thin_diagonal.png")
    root = auth_client.post(f"/api/projects/{pid}/patterns",
                            json={"params": {"grid_long_side": 40, "max_colors": 4}}).json()
    assert root["buildability"]["issues"]
    r = auth_client.post(f"/api/patterns/{root['id']}/apply-patch", json={"issue_index": 0})
    assert r.status_code == 200, r.text
    child = r.json()
    assert child["parent_id"] == root["id"] and child["origin"] == "patched"


def test_apply_patch_bad_index_is_400(auth_client, pattern):
    r = auth_client.post(f"/api/patterns/{pattern['id']}/apply-patch",
                         json={"issue_index": 9999})
    assert r.status_code == 400


def test_edits_create_child_and_reanalyze(auth_client, pattern):
    target = int(max(pattern["color_stats"], key=lambda k: pattern["color_stats"][k]))
    r = auth_client.post(f"/api/patterns/{pattern['id']}/edits",
                         json={"edits": [{"cell": [0, 0], "to": target},
                                         {"cell": [1, 1], "to": None}]})
    assert r.status_code == 200, r.text
    child = r.json()
    assert child["origin"] == "edited" and child["parent_id"] == pattern["id"]
    assert child["grid"][0][0] == target and child["grid"][1][1] is None
    assert child["buildability"] is not None


def test_edits_out_of_bounds_is_400(auth_client, pattern):
    r = auth_client.post(f"/api/patterns/{pattern['id']}/edits",
                         json={"edits": [{"cell": [999, 999], "to": 0}]})
    assert r.status_code == 400


def test_edits_empty_is_422(auth_client, pattern):
    r = auth_client.post(f"/api/patterns/{pattern['id']}/edits", json={"edits": []})
    assert r.status_code == 422       # Pydantic min_length=1 先拦下


def test_feedback_is_recorded(auth_client, pattern, db):
    from sqlalchemy import select

    from app.models import Feedback
    r = auth_client.post(f"/api/patterns/{pattern['id']}/feedback",
                         json={"kind": "断裂", "cells": [[3, 4], [3, 5]], "note": "发尾断了"})
    assert r.status_code == 204
    fb = db.scalars(select(Feedback)).all()
    assert fb and fb[-1].cells == [[3, 4], [3, 5]] and fb[-1].kind == "断裂"


def test_project_detail_lists_version_tree(auth_client, pattern):
    r = auth_client.get(f"/api/projects/{pattern['project_id']}")
    assert r.status_code == 200
    briefs = r.json()["patterns"]
    assert any(b["id"] == pattern["id"] for b in briefs)
    assert briefs[0]["n_colors"] > 0


def test_cannot_touch_other_users_pattern(auth_client, client, pattern, invite_other):
    client.cookies.clear()
    client.post("/api/auth/register",
                json={"username": "thief", "password": "pw12345678", "invite_code": "OTHER"})
    assert client.get(f"/api/patterns/{pattern['id']}").status_code == 404
    assert client.post(f"/api/patterns/{pattern['id']}/edits",
                       json={"edits": [{"cell": [0, 0], "to": 0}]}).status_code == 404



def test_thumb_is_one_pixel_per_cell(auth_client, pattern):
    import io
    from PIL import Image
    r = auth_client.get(f"/api/patterns/{pattern['id']}/thumb")
    assert r.status_code == 200
    # 图纸不可变，缩略图可以永久缓存；但它在登录态后面，不能进共享缓存
    assert "immutable" in r.headers["cache-control"]
    assert "private" in r.headers["cache-control"]
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (len(pattern["grid"][0]), len(pattern["grid"]))
    assert img.mode == "RGBA"


def test_thumb_is_transparent_where_cells_are_empty(auth_client):
    """透明底的图，空格在缩略图里必须是透明的，不能被填成黑或白。"""
    import io
    import numpy as np
    from PIL import Image
    pid = _project(auth_client, "thin_diagonal.png")
    pat = auth_client.post(f"/api/projects/{pid}/patterns",
                           json={"params": {"grid_long_side": 24}}).json()
    grid = np.array([[-1 if v is None else v for v in row] for row in pat["grid"]])
    assert (grid == -1).any(), "样本应当有空格，否则这个测试什么也没测"

    a = np.asarray(Image.open(io.BytesIO(
        auth_client.get(f"/api/patterns/{pat['id']}/thumb").content)))
    assert (a[grid == -1, 3] == 0).all()
    assert (a[grid != -1, 3] == 255).all()


def test_cannot_read_other_users_thumb(auth_client, client, pattern, invite_other):
    client.cookies.clear()
    client.post("/api/auth/register", json={"username": "peeker", "password": "pw12345678",
                                            "invite_code": "OTHER"})
    assert client.get(f"/api/patterns/{pattern['id']}/thumb").status_code == 404


# ---- 连续调参只留最后一版 ---------------------------------------------------

def _recompute(auth_client, pid, replaces=None, smoothness=2.0):
    body = {"params": {"grid_long_side": 20, "max_colors": 5, "smoothness": smoothness}}
    if replaces:
        body["replaces"] = replaces
    r = auth_client.post(f"/api/projects/{pid}/patterns", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _version_ids(auth_client, pid):
    return [p["id"] for p in auth_client.get(f"/api/projects/{pid}").json()["patterns"]]


def test_consecutive_tweaks_replace_the_previous_draft(auth_client):
    pid = _project(auth_client)
    a = _recompute(auth_client, pid, smoothness=3.5)
    b = _recompute(auth_client, pid, replaces=a["id"], smoothness=2.5)
    c = _recompute(auth_client, pid, replaces=b["id"], smoothness=1.5)

    assert b["replaced_id"] == a["id"] and c["replaced_id"] == b["id"]
    assert _version_ids(auth_client, pid) == [c["id"]]      # 拖三下滑块，只剩一版


def test_without_replaces_nothing_is_deleted(auth_client):
    pid = _project(auth_client)
    a = _recompute(auth_client, pid)
    b = _recompute(auth_client, pid)
    assert b["replaced_id"] is None
    assert set(_version_ids(auth_client, pid)) == {a["id"], b["id"]}


def test_never_discards_a_version_that_has_children(auth_client):
    """手改会以它为父版本；parent_id 是 SET NULL，删了会让手改版变成孤儿。"""
    pid = _project(auth_client)
    a = _recompute(auth_client, pid)
    edited = auth_client.post(f"/api/patterns/{a['id']}/edits",
                              json={"edits": [{"cell": [0, 0], "to": None}]}).json()
    b = _recompute(auth_client, pid, replaces=a["id"])
    assert b["replaced_id"] is None
    assert {a["id"], edited["id"], b["id"]} <= set(_version_ids(auth_client, pid))


def test_never_discards_an_edited_version(auth_client):
    """手改、修复出来的是用户的劳动。"""
    pid = _project(auth_client)
    a = _recompute(auth_client, pid)
    edited = auth_client.post(f"/api/patterns/{a['id']}/edits",
                              json={"edits": [{"cell": [0, 0], "to": None}]}).json()
    b = _recompute(auth_client, pid, replaces=edited["id"])
    assert b["replaced_id"] is None
    assert edited["id"] in _version_ids(auth_client, pid)


def test_never_discards_a_version_with_feedback(auth_client, db):
    """feedback 是 CASCADE：删了版本会把用户的实拼反馈一起删掉。"""
    from app.models import Feedback
    pid = _project(auth_client)
    a = _recompute(auth_client, pid)
    auth_client.post(f"/api/patterns/{a['id']}/feedback", json={"kind": "断裂", "cells": []})
    b = _recompute(auth_client, pid, replaces=a["id"])
    assert b["replaced_id"] is None
    assert a["id"] in _version_ids(auth_client, pid)
    assert db.query(Feedback).count() == 1


def test_cannot_discard_a_version_from_another_project(auth_client):
    p1, p2 = _project(auth_client), _project(auth_client)
    a = _recompute(auth_client, p1)
    b = _recompute(auth_client, p2, replaces=a["id"])
    assert b["replaced_id"] is None
    assert a["id"] in _version_ids(auth_client, p1)


def test_replacing_something_already_gone_is_harmless(auth_client):
    """两个请求撞车时第二个要替换的那版可能已经被删了——照常出图就行。"""
    import uuid
    pid = _project(auth_client)
    b = _recompute(auth_client, pid, replaces=str(uuid.uuid4()))
    assert b["replaced_id"] is None
    assert _version_ids(auth_client, pid) == [b["id"]]
