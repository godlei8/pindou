"""人脸检测：给五官"开小灶"用。

人像实拍出图时眼睛、鼻子会被平滑抹掉。诊断结论（2026-09-21，见 spec）：
- 平滑对所有边界罚一样的分，单格瞳孔、鼻孔这种高反差小特征会被当成杂点抹平；
- 全图改成"反差越大越少抹"能救回瞳孔，但头发、背景的杂点也一起留下，散点 3.29% → 4.43%；
- **只在五官周围放松**，救回瞳孔的同时散点只多 0.04 个百分点。

所以要知道五官在哪。用 OpenCV 自带接口的 YuNet（模型随附在 assets/models，MIT 许可）。
它除了脸框还给五个关键点：右眼、左眼、鼻尖、右嘴角、左嘴角。

**这里任何失败都只当"没检测到脸"**：模型文件丢了、OpenCV 版本不支持、图片太怪——
都不能让出图失败，最多是五官没有额外照顾。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

MODEL_PATH = (Path(__file__).resolve().parents[1]
              / "assets" / "models" / "face_detection_yunet_2023mar.onnx")
#: 检测时把长边缩到这么大：YuNet 在这个尺度上又快又准（实测 4096px 原图约 20ms）
DETECT_LONG_SIDE = 640
SCORE_THRESHOLD = 0.7
#: 人脸宽度低于这么多格时，五官（尤其眼睛）容易糊。实测：同一张照片脸宽 21 格时
#: 眉眼间隔不到一格、左眼瞳孔丢失；32 格时双眼和鼻孔都保得住。
MIN_FACE_CELLS = 30


@dataclass(frozen=True)
class Face:
    """坐标全部归一化到 0–1（相对原图宽高），和网格尺寸无关。"""
    box: tuple[float, float, float, float]          # x, y, w, h
    landmarks: tuple[tuple[float, float], ...]      # 右眼 左眼 鼻尖 右嘴角 左嘴角
    score: float

    def to_dict(self) -> dict:
        return {"box": list(self.box), "landmarks": [list(p) for p in self.landmarks],
                "score": round(self.score, 3)}


@lru_cache(maxsize=1)
def _detector_factory():
    import cv2
    if not MODEL_PATH.exists() or not hasattr(cv2, "FaceDetectorYN"):
        return None
    return cv2


def detect_faces(rgb: np.ndarray) -> list[Face]:
    """rgb: (h, w, 3)，0–255 的 uint8 或 0–1 的浮点都行。检测不到或出任何错都返回 []。"""
    try:
        cv2 = _detector_factory()
        if cv2 is None or rgb.ndim != 3 or rgb.shape[0] < 16 or rgb.shape[1] < 16:
            return []
        img = rgb[..., :3]
        if img.dtype != np.uint8:
            img = (np.clip(img, 0, 1) * 255).astype(np.uint8)
        h, w = img.shape[:2]
        s = min(1.0, DETECT_LONG_SIDE / max(h, w))
        small = cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))),
                           interpolation=cv2.INTER_AREA) if s < 1 else img
        bgr = np.ascontiguousarray(small[..., ::-1])
        sw, sh = bgr.shape[1], bgr.shape[0]
        det = cv2.FaceDetectorYN.create(str(MODEL_PATH), "", (sw, sh),
                                        SCORE_THRESHOLD, 0.3, 5000)
        _, found = det.detect(bgr)
        if found is None:
            return []
        faces = []
        for f in found:
            x, y, fw, fh = (float(v) for v in f[:4])
            lm = tuple((float(f[4 + 2 * i]) / sw, float(f[5 + 2 * i]) / sh) for i in range(5))
            faces.append(Face(box=(max(0.0, x / sw), max(0.0, y / sh), fw / sw, fh / sh),
                              landmarks=lm, score=float(f[-1])))
        faces.sort(key=lambda fc: -fc.box[2] * fc.box[3])      # 大脸在前
        return faces
    except Exception:                                            # 绝不拖垮出图
        log.exception("人脸检测失败，按没有人脸处理")
        return []


def feature_mask(faces: list[Face], rows: int, cols: int) -> np.ndarray:
    """五官窗口：两只眼睛、鼻子、嘴巴周围的椭圆，按格子给出布尔掩码。

    只罩五官、不罩整张脸：实测整张脸都放松时额头会多出一块浅粉斑，
    罩五官就只救瞳孔、鼻孔、唇线，脸颊照常抹平。"""
    m = np.zeros((rows, cols), dtype=bool)
    if not faces:
        return m
    yy, xx = np.mgrid[0:rows, 0:cols]
    x, y = (xx + 0.5) / cols, (yy + 0.5) / rows
    for f in faces:
        _, _, fw, fh = f.box
        (rex, rey), (lex, ley), (nx, ny), (mx1, my1), (mx2, my2) = f.landmarks
        for ex, ey in ((rex, rey), (lex, ley)):
            m |= ((x - ex) / (0.16 * fw)) ** 2 + ((y - ey) / (0.09 * fh)) ** 2 <= 1
        m |= ((x - nx) / (0.12 * fw)) ** 2 + ((y - ny) / (0.08 * fh)) ** 2 <= 1
        cx, cy = (mx1 + mx2) / 2, (my1 + my2) / 2
        half = max(abs(mx2 - mx1) / 2, 0.05 * fw)
        m |= ((x - cx) / (half * 1.4)) ** 2 + ((y - cy) / (0.08 * fh)) ** 2 <= 1
    return m


def face_cells_wide(face: Face, cols: int) -> int:
    return int(round(face.box[2] * cols))


def suggested_long_side(face: Face, rows: int, cols: int, min_cells: int = MIN_FACE_CELLS) -> int:
    """要让这张脸至少 min_cells 格宽，长边需要多少格。"""
    long_side = max(rows, cols)
    cells = max(1e-6, face.box[2] * cols)
    return int(np.ceil(long_side * min_cells / cells))


#: 五官窗口里的边权 = max(FLOOR, exp(-ΔE² / 2σ²))：原图反差越大，越不强行抹平。
#: σ=12、底 0.3 是在真实人像上试出来的：救回瞳孔，全图散点只多 0.04 个百分点。
FEATURE_SIGMA = 12.0
FEATURE_FLOOR = 0.3


def feature_edge_weights(faces: list[Face], cell_lab: np.ndarray, mask: np.ndarray) -> np.ndarray | None:
    """给 assign_labels 的每条边一个平滑倍数：五官窗口里按原图反差放松，其余一律 1。
    没有人脸就返回 None（图割走原来的逻辑，结果一模一样）。"""
    if not faces:
        return None
    from app.core.assign import _edges
    rows, cols = mask.shape
    feat = feature_mask(faces, rows, cols).ravel()
    p, q = _edges(mask)
    w = np.ones(len(p))
    inside = feat[p] | feat[q]
    if inside.any():
        L = cell_lab.reshape(-1, 3)
        de = np.sqrt(((L[p[inside]] - L[q[inside]]) ** 2).sum(-1))
        w[inside] = np.maximum(FEATURE_FLOOR, np.exp(-de ** 2 / (2 * FEATURE_SIGMA ** 2)))
    return w
