import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.models import Pattern, Project, User
from app.services import patterns as svc
from app.services.palettes import load_core_palette

FIXTURES = Path(__file__).parent / "fixtures" / "images"


@pytest.fixture
def user(db):
    u = User(username="pat-user", password_hash="x", ai_quota=5)
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def palette():
    return load_core_palette("mard")


def _png(color=(200, 60, 60), size=(120, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


# ---------- 参数校验 ----------

def test_params_defaults_and_roundtrip():
    p = svc.params_from_dict({})
    assert p.grid_long_side == 58 and p.smoothness == 2.0 and p.dither is False
    assert svc.params_from_dict(svc.params_to_dict(p)).max_colors == p.max_colors


@pytest.mark.parametrize("bad", [
    {"grid_long_side": 1}, {"grid_long_side": 500},
    {"max_colors": -1}, {"max_colors": 1}, {"max_colors": 999},
    {"smoothness": -1}, {"smoothness": 1000},
])
def test_params_out_of_range_rejected(bad):
    with pytest.raises(svc.PatternError):
        svc.params_from_dict(bad)


def test_params_ignores_unknown_keys():
    p = svc.params_from_dict({"grid_long_side": 40, "evil": "rm -rf"})
    assert p.grid_long_side == 40 and not hasattr(p, "evil")


# ---------- 网格序列化 ----------

def test_grid_db_roundtrip_preserves_empty_cells():
    g = np.array([[0, -1], [3, 2]], dtype=np.int16)
    as_db = svc.grid_to_db(g)
    assert as_db == [[0, None], [3, 2]]
    back = svc.grid_from_db(as_db)
    assert back.dtype == np.int16 and np.array_equal(back, g)


# ---------- 项目与生成 ----------

def test_create_project_stores_image_and_record(db, user):
    proj = svc.create_project(db, user.id, "测试", _png())
    assert isinstance(proj, Project) and proj.user_id == user.id
    assert svc.storage_of().exists(proj.source_image_path)


def test_create_project_rejects_oversize(db, user):
    with pytest.raises(svc.PatternError, match="过大"):
        svc.create_project(db, user.id, "big", b"x" * (21 * 1024 * 1024))


def test_create_project_rejects_non_image(db, user):
    with pytest.raises(svc.PatternError, match="格式"):
        svc.create_project(db, user.id, "bad", b"not an image at all")


def test_generate_persists_grid_and_report(db, user, palette):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    pat = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 30, "max_colors": 6}))
    assert isinstance(pat, Pattern) and pat.origin == "generated" and pat.parent_id is None
    assert len(pat.grid) == 30 and len(pat.grid[0]) == 30
    assert pat.color_stats and pat.buildability is not None
    assert "score" in pat.buildability and "confetti_pct" in pat.buildability
    assert pat.params["grid_long_side"] == 30


def test_generate_survives_buildability_failure(db, user, monkeypatch):
    """可拼性是附加环节——它炸了也必须出图。"""
    import app.services.patterns as m
    monkeypatch.setattr(m, "_analyze_report", lambda *a, **k: None)
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    pat = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 4}))
    assert pat.grid and pat.buildability is None


# ---------- 修复建议 ----------

def test_apply_issue_creates_child_version(db, user, palette):
    # 必须用透明底样本：不透明白底的图每格都填满，形状上没有破绽，永远零问题
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "thin_diagonal.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 40, "max_colors": 4}))
    assert root.buildability["issues"], "细斜线样本应该产出问题"
    root_grid = [row[:] for row in root.grid]
    child = svc.apply_issue(db, root, 0)
    assert child.parent_id == root.id and child.origin == "patched"
    assert child.applied_patch["type"] == root.buildability["issues"][0]["type"]
    assert child.grid != root_grid
    assert db.get(Pattern, root.id).grid == root_grid      # 原版本不被改动


def test_bridge_with_clear_is_the_preferred_action(db, user, palette):
    """悬空/虚连的解法是补透明豆——保持图形不变，这是实拼社区的标准解法。
    只靠一个角连着的地方出图时就自动补好（不补实物一拿就散）；离得远的两块留给用户点「应用修复」。"""
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "thin_diagonal.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 40, "max_colors": 4}))
    clear_idx = palette.clear_index
    flat_before = [v for row in root.grid for v in row]
    assert flat_before.count(clear_idx) > 0, "对角线上的拐点应该已经自动补了透明豆"
    assert not any(i["type"] == "diagonal_link" for i in root.buildability["issues"])
    assert {i["action"] for i in root.buildability["issues"]} == {"bridge_with_clear"}

    child = svc.apply_issue(db, root, 0)
    flat_after = [v for row in child.grid for v in row]
    assert flat_after.count(clear_idx) > flat_before.count(clear_idx)


def test_apply_issue_rejects_bad_index(db, user):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 4}))
    with pytest.raises(svc.PatternError):
        svc.apply_issue(db, root, 9999)


# ---------- 手工编辑 ----------

def test_apply_manual_edits_writes_cells_and_reanalyzes(db, user):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 6}))
    target = int(max(root.color_stats, key=lambda k: root.color_stats[k]))
    before_00 = root.grid[0][0]
    child = svc.apply_manual_edits(db, root, [
        {"cell": [0, 0], "to": target},
        {"cell": [1, 1], "to": None},
    ])
    assert child.origin == "edited" and child.parent_id == root.id
    assert child.grid[0][0] == target and child.grid[1][1] is None
    assert child.buildability is not None
    assert child.manual_edits[0]["cell"] == [0, 0]
    assert child.manual_edits[0]["from"] == before_00


def test_manual_edits_reject_out_of_bounds(db, user):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 4}))
    with pytest.raises(svc.PatternError, match="越界"):
        svc.apply_manual_edits(db, root, [{"cell": [99, 99], "to": 0}])


def test_manual_edits_reject_unknown_color_index(db, user, palette):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 4}))
    with pytest.raises(svc.PatternError, match="色号"):
        svc.apply_manual_edits(db, root, [{"cell": [0, 0], "to": len(palette) + 10}])


def test_manual_edits_empty_list_rejected(db, user):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 4}))
    with pytest.raises(svc.PatternError):
        svc.apply_manual_edits(db, root, [])


# ---------- 导出 ----------

def test_export_png_and_pdf_and_materials(db, user, palette):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    pat = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 5}))
    png = svc.export_png(pat, palette, cell_px=12)
    assert Image.open(io.BytesIO(png)).size[0] > 200
    pdf = svc.export_pdf(pat, palette)
    assert pdf[:5] == b"%PDF-"
    mats = svc.materials_of(pat, palette)
    assert mats and mats[0]["count"] >= mats[-1]["count"]
    assert sum(m["count"] for m in mats) == sum(pat.color_stats.values())


def test_max_colors_zero_means_unlimited():
    assert svc.params_from_dict({"max_colors": 0}).max_colors == 0
    assert svc.params_from_dict({}).max_colors == 0          # 默认就是不限
