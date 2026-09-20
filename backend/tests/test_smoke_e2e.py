"""端到端冒烟：注册 → 上传 → 尺寸推荐 → 出图 → 修图 → 编辑 → 反馈 → 导出，一条龙。"""
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "images"


def test_full_user_journey(client, db, monkeypatch):
    from app.models import InviteCode
    from app.services import auth
    monkeypatch.setattr(auth, "_ROUNDS", 4)
    db.add(InviteCode(code="SMOKE", max_uses=1))
    db.flush()

    # 注册
    r = client.post("/api/auth/register",
                    json={"username": "smoke", "password": "pw12345678",
                          "invite_code": "SMOKE"})
    assert r.status_code == 201

    # 上传
    r = client.post("/api/projects", data={"name": "冒烟"},
                    files={"file": ("cartoon.png", (FIXTURES / "cartoon.png").read_bytes(),
                                    "image/png")})
    assert r.status_code == 201
    pid = r.json()["id"]

    # 尺寸推荐
    sizes = client.get(f"/api/projects/{pid}/suggest-sizes?base=40").json()
    assert len(sizes) == 3

    # 同步出图
    pat = client.post(f"/api/projects/{pid}/patterns",
                      json={"params": {"grid_long_side": sizes[1]["long_side"],
                                       "max_colors": 8}}).json()
    assert pat["buildability"]["score"] > 0
    assert pat["materials"]

    # 手工改一格
    target = int(max(pat["color_stats"], key=lambda k: pat["color_stats"][k]))
    edited = client.post(f"/api/patterns/{pat['id']}/edits",
                         json={"edits": [{"cell": [0, 0], "to": target}]}).json()
    assert edited["grid"][0][0] == target

    # 实拼反馈
    assert client.post(f"/api/patterns/{edited['id']}/feedback",
                       json={"kind": "断裂", "cells": [[1, 1]],
                             "note": "试试"}).status_code == 204

    # 导出
    png = client.get(f"/api/patterns/{edited['id']}/export?format=png&cell_px=8")
    pdf = client.get(f"/api/patterns/{edited['id']}/export?format=pdf")
    assert png.status_code == 200 and pdf.content[:5] == b"%PDF-"

    # 版本树可见
    detail = client.get(f"/api/projects/{pid}").json()
    assert len(detail["patterns"]) >= 2


def test_patch_journey_on_a_problematic_pattern(client, db, monkeypatch):
    """带问题的图纸：体检 → 接受补透明豆建议 → 问题变少。"""
    from app.models import InviteCode
    from app.services import auth
    monkeypatch.setattr(auth, "_ROUNDS", 4)
    db.add(InviteCode(code="SMOKE2", max_uses=1))
    db.flush()
    client.post("/api/auth/register",
                json={"username": "smoke2", "password": "pw12345678",
                      "invite_code": "SMOKE2"})
    pid = client.post("/api/projects", data={"name": "斜线"},
                      files={"file": ("thin_diagonal.png",
                                      (FIXTURES / "thin_diagonal.png").read_bytes(),
                                      "image/png")}).json()["id"]
    root = client.post(f"/api/projects/{pid}/patterns",
                       json={"params": {"grid_long_side": 40, "max_colors": 4}}).json()
    before = len(root["buildability"]["issues"])
    assert before > 0

    child = client.post(f"/api/patterns/{root['id']}/apply-patch",
                        json={"issue_index": 0}).json()
    assert child["origin"] == "patched"
    assert len(child["buildability"]["issues"]) < before
