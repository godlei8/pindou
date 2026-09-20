import io
from pathlib import Path

import pytest
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures" / "images"


@pytest.fixture
def pattern_id(auth_client):
    pid = auth_client.post("/api/projects", data={"name": "t"},
                           files={"file": ("logo.png", (FIXTURES / "logo.png").read_bytes(),
                                           "image/png")}).json()["id"]
    return auth_client.post(f"/api/projects/{pid}/patterns",
                            json={"params": {"grid_long_side": 16,
                                             "max_colors": 4}}).json()["id"]


def test_export_png(auth_client, pattern_id):
    r = auth_client.get(f"/api/patterns/{pattern_id}/export?format=png&cell_px=10")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).size[0] >= 160


def test_export_pdf_is_real_pdf(auth_client, pattern_id):
    r = auth_client.get(f"/api/patterns/{pattern_id}/export?format=pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert "attachment" in r.headers.get("content-disposition", "")


def test_export_unknown_format_is_400(auth_client, pattern_id):
    assert auth_client.get(f"/api/patterns/{pattern_id}/export?format=svg").status_code == 400


def test_palettes_and_colors_endpoints(auth_client, db):
    from app.services.palettes import seed_palettes
    seed_palettes(db)
    db.flush()
    pl = auth_client.get("/api/palettes")
    assert pl.status_code == 200 and pl.json()
    colors = auth_client.get("/api/palettes/mard/colors")
    assert colors.status_code == 200
    body = colors.json()
    assert len(body) >= 291
    assert body[0]["index"] == 0 and body[0]["hex"].startswith("#")
    assert any(c["role"] == "clear" for c in body)


def test_palette_colors_index_matches_grid_values(auth_client, pattern_id):
    """grid 里存的是全局色卡索引，前端靠这个索引上色——两者必须对得上。"""
    pat = auth_client.get(f"/api/patterns/{pattern_id}").json()
    colors = auth_client.get("/api/palettes/mard/colors").json()
    by_index = {c["index"]: c for c in colors}
    used = {v for row in pat["grid"] for v in row if v is not None}
    assert used and used <= set(by_index)
    for m in pat["materials"]:
        assert by_index[m["index"]]["code"] == m["code"]


def test_style_presets_endpoint(auth_client, db):
    from app.models import StylePreset
    db.add(StylePreset(name="Q版盲盒", prompt="粗轮廓 纯色平涂", params={}))
    db.flush()
    r = auth_client.get("/api/style-presets")
    assert r.status_code == 200 and r.json()[0]["name"] == "Q版盲盒"
