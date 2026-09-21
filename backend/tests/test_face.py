"""五官开小灶：只在眼睛、鼻子、嘴巴周围放松平滑。

背景：人像实拍里单格瞳孔、鼻孔会被平滑当成杂点抹掉。全图放松能救回来但杂点暴增
（散点 3.29% → 4.43%）；只在五官窗口放松，救回瞳孔的同时散点只多 0.04 个百分点。

注：仓库里不放真人照片，所以"真的检测到一张脸"这条路径在这里只能测到"跑得通、不误报"；
真实人像上的效果在本地用用户的照片验收过（见提交说明）。
"""
import numpy as np
import pytest

from app.core import face as face_mod
from app.core.assign import _edges, assign_labels
from app.core.face import Face, feature_edge_weights, feature_mask, suggested_long_side

# 一张正脸：脸框占画面中间，五个关键点在常见位置
FACE = Face(box=(0.3, 0.2, 0.4, 0.5),
            landmarks=((0.42, 0.38), (0.58, 0.38), (0.5, 0.5), (0.43, 0.6), (0.57, 0.6)),
            score=0.95)


# ---- 检测：失败一律当"没有脸"，绝不拖垮出图 ------------------------------------

def test_missing_model_means_no_faces(monkeypatch, tmp_path):
    monkeypatch.setattr(face_mod, "MODEL_PATH", tmp_path / "nope.onnx")
    face_mod._detector_factory.cache_clear()
    try:
        assert face_mod.detect_faces(np.zeros((200, 200, 3), np.uint8)) == []
    finally:
        face_mod._detector_factory.cache_clear()


def test_weird_input_means_no_faces():
    assert face_mod.detect_faces(np.zeros((5, 5, 3), np.uint8)) == []      # 太小
    assert face_mod.detect_faces(np.zeros((100, 100), np.uint8)) == []      # 不是彩色


def test_a_blank_image_has_no_faces():
    """跑通真实模型，并且不在纯色图上误报。"""
    assert face_mod.detect_faces(np.full((300, 400, 3), 200, np.uint8)) == []


def test_float_input_is_accepted():
    assert face_mod.detect_faces(np.full((300, 400, 3), 0.8, np.float32)) == []


def test_detector_crash_does_not_break_generation(monkeypatch):
    """检测器抛异常，出图照常。"""
    import io

    from PIL import Image

    from app.core import pipeline
    from app.core.palette import Palette
    from app.core.types import Params

    class Boom:
        class FaceDetectorYN:
            @staticmethod
            def create(*a, **k):
                raise RuntimeError("模型坏了")
    monkeypatch.setattr(face_mod, "_detector_factory", lambda: Boom)
    buf = io.BytesIO()
    Image.new("RGB", (120, 120), (200, 150, 130)).save(buf, format="PNG")
    res = pipeline.run(buf.getvalue(), Params(grid_long_side=24), Palette.load("mard"))
    assert res.grid.shape == (24, 24)
    assert res.faces == []


# ---- 五官窗口 ------------------------------------------------------------------

def _cell(x, y, rows, cols):
    return int(y * rows), int(x * cols)


def test_feature_mask_covers_eyes_nose_and_mouth_but_not_cheeks():
    rows = cols = 60
    m = feature_mask([FACE], rows, cols)
    for x, y in FACE.landmarks[:3]:
        assert m[_cell(x, y, rows, cols)], f"关键点 ({x},{y}) 应在窗口里"
    assert m[_cell(0.5, 0.6, rows, cols)], "两嘴角中间（嘴）应在窗口里"
    assert not m[_cell(0.34, 0.5, rows, cols)], "脸颊不该放松"
    assert not m[_cell(0.5, 0.24, rows, cols)], "额头不该放松"
    assert not m[_cell(0.05, 0.05, rows, cols)], "背景不该放松"


def test_no_faces_means_no_special_weights():
    """没有脸 → None → 图割走原来的逻辑，结果一模一样。"""
    lab = np.zeros((10, 10, 3))
    assert feature_edge_weights([], lab, np.ones((10, 10), bool)) is None


def test_weights_relax_only_high_contrast_edges_inside_the_windows():
    rows = cols = 60
    lab = np.full((rows, cols, 3), [70.0, 15.0, 15.0])            # 肤色
    er, ec = _cell(*FACE.landmarks[0], rows, cols)
    lab[er, ec] = [30.0, 5.0, 5.0]                                 # 窗口里一个暗瞳孔
    lab[50, 5] = [30.0, 5.0, 5.0]                                  # 窗口外同样暗的一格
    mask = np.ones((rows, cols), bool)
    w = feature_edge_weights([FACE], lab, mask)
    p, q = _edges(mask)
    idx = lambda r, c: r * cols + c
    pupil_edges = (p == idx(er, ec)) | (q == idx(er, ec))
    outside_edges = (p == idx(50, 5)) | (q == idx(50, 5))
    assert (w[pupil_edges] < 0.5).all(), "瞳孔四周是高反差边，应该放松"
    assert (w[outside_edges] == 1).all(), "窗口外一律不放松"
    assert w.min() >= face_mod.FEATURE_FLOOR
    # 窗口里的平坦肤色边几乎不放松——所以脸颊、窗口内的皮肤照样会被抹平
    flat_inside = feature_mask([FACE], rows, cols).ravel()
    flat = flat_inside[p] & flat_inside[q] & ~pupil_edges
    assert np.allclose(w[flat], 1.0)


# ---- 图割：放松的边保得住单格特征 ------------------------------------------------

def test_relaxed_edges_keep_a_single_cell_feature():
    """中心一格略偏好另一种颜色（数据代价差 5）。
    均匀平滑 λ=2：四条边省下 8 > 5，它被抹掉；四条边放松到 0.3 倍：只省 2.4 < 5，它留下。"""
    cost = np.zeros((5, 5, 2))
    cost[..., 1] = 20                                              # 周围都强烈偏好 0
    cost[2, 2] = [5, 0]                                            # 中心偏好 1
    mask = np.ones((5, 5), bool)
    assert assign_labels(cost, mask, 2.0)[2, 2] == 0               # 均匀平滑：被抹掉

    p, q = _edges(mask)
    w = np.ones(len(p))
    center = 2 * 5 + 2
    w[(p == center) | (q == center)] = 0.3
    assert assign_labels(cost, mask, 2.0, edge_weight=w)[2, 2] == 1


def test_edge_weight_of_wrong_length_is_rejected():
    with pytest.raises(ValueError):
        assign_labels(np.zeros((3, 3, 2)), np.ones((3, 3), bool), 1.0, edge_weight=np.ones(3))


# ---- 流水线接线 ------------------------------------------------------------------

def test_pipeline_relaxes_smoothing_around_detected_features(monkeypatch):
    import io

    from PIL import Image

    from app.core import pipeline
    from app.core.palette import Palette
    from app.core.types import Params

    monkeypatch.setattr(pipeline.face, "detect_faces", lambda rgb: [FACE])
    seen = {}
    real = pipeline.assign_labels

    def spy(cost, mask, lam, locked=None, **kw):
        seen["w"] = kw.get("edge_weight")
        seen["mask"] = mask
        return real(cost, mask, lam, locked, **kw)
    monkeypatch.setattr(pipeline, "assign_labels", spy)

    img = np.full((240, 240, 3), (225, 180, 160), np.uint8)
    img[88:96, 96:104] = (60, 40, 35)                              # 右眼处一个暗点
    buf = io.BytesIO(); Image.fromarray(img).save(buf, format="PNG")
    res = pipeline.run(buf.getvalue(), Params(grid_long_side=60), Palette.load("mard"))

    assert res.faces == [FACE]
    assert seen["w"] is not None and (seen["w"] < 1).any()


def test_pipeline_without_faces_uses_plain_smoothing(monkeypatch):
    import io

    from PIL import Image

    from app.core import pipeline
    from app.core.palette import Palette
    from app.core.types import Params

    monkeypatch.setattr(pipeline.face, "detect_faces", lambda rgb: [])
    seen = {}
    real = pipeline.assign_labels
    monkeypatch.setattr(pipeline, "assign_labels",
                        lambda c, m, l, locked=None, **kw: (seen.setdefault("w", kw.get("edge_weight")),
                                                            real(c, m, l, locked, **kw))[1])
    buf = io.BytesIO(); Image.new("RGB", (120, 120), (200, 150, 130)).save(buf, format="PNG")
    pipeline.run(buf.getvalue(), Params(grid_long_side=24), Palette.load("mard"))
    assert seen["w"] is None


# ---- 脸太小时建议的格数 ------------------------------------------------------------

def test_suggested_long_side_makes_the_face_wide_enough():
    # 这张脸占画面宽度的 40%：58 格时约 23 格宽，不够 30
    n = suggested_long_side(FACE, rows=58, cols=58)
    assert n == 75                                                 # ceil(58 × 30 / 23.2)
    assert FACE.box[2] * n >= 30


# ---- 图纸上的"脸太小"提示 ------------------------------------------------------------

def _pattern_with_face(auth_client, monkeypatch, face, long_side):
    from pathlib import Path

    from app.core import pipeline
    monkeypatch.setattr(pipeline.face, "detect_faces", lambda rgb: [face])
    img = (Path(__file__).parent / "fixtures" / "images" / "logo.png").read_bytes()
    pid = auth_client.post("/api/projects", data={"name": "t"},
                           files={"file": ("a.png", img, "image/png")}).json()["id"]
    r = auth_client.post(f"/api/projects/{pid}/patterns", json={"params": {"grid_long_side": long_side}})
    assert r.status_code == 200, r.text
    return r.json()


def test_small_face_gets_a_suggested_size(auth_client, monkeypatch):
    pat = _pattern_with_face(auth_client, monkeypatch, FACE, 40)          # 脸宽 0.4 × 40 = 16 格
    hint = pat["face_hint"]
    assert hint["too_small"] is True and hint["cells_wide"] == 16
    assert hint["suggested_long_side"] * FACE.box[2] >= hint["min_cells"]


def test_big_enough_face_gets_no_suggestion(auth_client, monkeypatch):
    pat = _pattern_with_face(auth_client, monkeypatch, FACE, 100)         # 40 格宽，够了
    assert pat["face_hint"]["too_small"] is False
    assert pat["face_hint"]["suggested_long_side"] is None


def test_no_face_no_hint(auth_client, monkeypatch):
    from pathlib import Path

    from app.core import pipeline
    monkeypatch.setattr(pipeline.face, "detect_faces", lambda rgb: [])
    img = (Path(__file__).parent / "fixtures" / "images" / "logo.png").read_bytes()
    pid = auth_client.post("/api/projects", data={"name": "t"},
                           files={"file": ("a.png", img, "image/png")}).json()["id"]
    pat = auth_client.post(f"/api/projects/{pid}/patterns", json={"params": {}}).json()
    assert pat["face_hint"] is None


def test_edited_versions_keep_the_face_info(auth_client, monkeypatch):
    """手改出来的子版本不重新检测，沿用父版本的人脸信息，提示不能凭空消失。"""
    pat = _pattern_with_face(auth_client, monkeypatch, FACE, 40)
    child = auth_client.post(f"/api/patterns/{pat['id']}/edits",
                             json={"edits": [{"cell": [0, 0], "to": None}]}).json()
    assert child["face_hint"] == pat["face_hint"]


def test_suggestion_is_capped_at_the_max_grid(auth_client, monkeypatch):
    tiny = Face(box=(0.45, 0.45, 0.05, 0.06), landmarks=FACE.landmarks, score=0.9)
    pat = _pattern_with_face(auth_client, monkeypatch, tiny, 58)
    assert pat["face_hint"]["suggested_long_side"] == 200                # 界面上格数上限就是 200
