"""生成算法基准图：各种类型各一张，全部用代码画（不涉及版权），输出到 tests/fixtures/bench/。

    python scripts/make_bench_images.py

配合 scripts/benchmark_fidelity.py 批量出图、看还原度。类型：
  flat_*     平涂插画（有/无描边、细线稿、Q 版人脸、文字 logo、低分辨率、JPEG 压过的）
  soft_*     有柔和渐变/阴影的插画（不是平涂，也不是照片）
  photo_*    照片类（连续色调 + 噪点）
  pixel_*    像素画
真人照片不放仓库；benchmark 会额外去 data/uploads 里找本机上传过的照片一起测。
"""
from __future__ import annotations

import io
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "bench"
FONT = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / \
    "fusion-pixel-12px-zh_hans-subset.ttf"
S = 4                                   # 4 倍画再缩小 = 抗锯齿
INK = (59, 47, 35)


def _canvas(size, bg):
    im = Image.new("RGB", (size * S, size * S), bg)
    return im, ImageDraw.Draw(im)


def _done(im, size):
    return im.resize((size, size), Image.LANCZOS)


def _b(*v):
    return [x * S for x in v]


def flat_no_outline(size=480):
    """没有描边的色块：彩虹 + 云。浅色之间的边界最容易糊。"""
    im, d = _canvas(size, (255, 255, 255))
    for i, col in enumerate([(255, 107, 107), (255, 177, 66), (255, 221, 89),
                             (120, 214, 120), (99, 179, 237), (159, 122, 234)]):
        r = 190 - i * 22
        d.pieslice(_b(240 - r, 300 - r, 240 + r, 300 + r), 180, 360, fill=col)
    d.pieslice(_b(240 - 58, 300 - 58, 240 + 58, 300 + 58), 180, 360, fill=(255, 255, 255))
    for cx in (70, 410):
        for dx, dy, r in ((0, 0, 34), (30, 8, 26), (-30, 8, 26), (12, -18, 24)):
            d.ellipse(_b(cx + dx - r, 300 + dy - r, cx + dx + r, 300 + dy + r), fill=(214, 234, 248))
    return _done(im, size)


def flat_thin_lineart(size=480):
    """细线稿：2.5px 的线画一朵花，只有花心和两片叶子填色。线比格子细得多。"""
    im, d = _canvas(size, (255, 255, 255))
    w = int(2.5 * S)
    for k in range(6):
        a = math.radians(60 * k)
        cx, cy = 240 + 78 * math.cos(a), 190 + 78 * math.sin(a)
        d.ellipse(_b(cx - 50, cy - 50, cx + 50, cy + 50), fill=(255, 214, 224), outline=INK, width=w)
    d.ellipse(_b(200, 150, 280, 230), fill=(255, 219, 77), outline=INK, width=w)
    d.line(_b(240, 270, 240, 440), fill=INK, width=w)
    for sx in (-1, 1):
        d.polygon(_b(240, 380, 240 + sx * 80, 340, 240 + sx * 60, 400), fill=(120, 200, 120), outline=INK)
        d.line(_b(240, 380, 240 + sx * 80, 340, 240 + sx * 60, 400, 240, 380), fill=INK, width=w)
    return _done(im, size)


def flat_chibi_face(size=480):
    """Q 版人脸：头发、肤色、带高光的大眼睛、嘴、腮红，5px 描边。平涂人像的典型。"""
    im, d = _canvas(size, (230, 240, 255))
    w = 5 * S
    hair, skin = (92, 64, 51), (255, 224, 196)
    d.ellipse(_b(70, 50, 410, 400), fill=hair, outline=INK, width=w)            # 后发
    d.ellipse(_b(105, 110, 375, 400), fill=skin, outline=INK, width=w)          # 脸
    d.pieslice(_b(95, 60, 385, 330), 180, 360, fill=hair, outline=INK, width=w)  # 刘海
    d.polygon(_b(140, 195, 200, 150, 260, 200, 320, 150, 345, 195, 345, 150, 140, 150), fill=hair)
    for cx in (185, 295):
        d.ellipse(_b(cx - 24, 215, cx + 24, 285), fill=INK)
        d.ellipse(_b(cx - 16, 232, cx + 16, 282), fill=(80, 130, 200))
        d.ellipse(_b(cx - 16, 224, cx - 2, 240), fill=(255, 255, 255))
        d.ellipse(_b(cx + 4, 262, cx + 12, 270), fill=(255, 255, 255))
        bx = cx - 62 if cx < 240 else cx + 22
        d.ellipse(_b(bx, 295, bx + 40, 317), fill=(255, 170, 180))
    d.pieslice(_b(215, 300, 265, 350), 0, 180, fill=(200, 60, 80), outline=INK, width=3 * S)
    return _done(im, size)


def flat_logo_text(size=480):
    """粗体字 + 几何形：直角、细的笔画间隙。"""
    im, d = _canvas(size, (255, 250, 235))
    d.rounded_rectangle(_b(40, 120, 440, 360), radius=36 * S, fill=(200, 0, 32), outline=INK, width=6 * S)
    font = ImageFont.truetype(str(FONT), 132 * S)
    d.text((240 * S, 236 * S), "拼豆", font=font, fill=(255, 250, 235), anchor="mm")
    d.ellipse(_b(60, 60, 130, 130), fill=(255, 219, 77), outline=INK, width=5 * S)
    d.ellipse(_b(350, 350, 420, 420), fill=(0, 189, 53), outline=INK, width=5 * S)
    return _done(im, size)


def flat_lowres(size=128):
    """很小的图（128px 图标）：一格只有两三个像素。"""
    return flat_chibi_face(480).resize((size, size), Image.LANCZOS)


def flat_jpeg(size=480) -> Image.Image:
    """平涂图存成 JPEG（质量 72）：色块里满是压缩噪点，是网上找来的图最常见的样子。"""
    buf = io.BytesIO()
    flat_chibi_face(size).save(buf, format="JPEG", quality=72)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def soft_shaded(size=480):
    """有渐变和阴影的插画：一个苹果，径向高光 + 地面投影。既不是平涂也不是照片。"""
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    img = np.empty((size, size, 3), np.float32)
    img[:] = (250, 245, 235)
    shadow = np.exp(-(((x - 250) / 150) ** 2 + ((y - 400) / 26) ** 2))
    img -= shadow[..., None] * np.array([70, 70, 60], np.float32)
    r = np.hypot(x - 240, (y - 250) * 1.05)
    body = r < 150
    light = np.clip(1.15 - np.hypot(x - 190, y - 190) / 260, 0.35, 1.15)
    apple = np.stack([215 * light, 40 * light + 10, 45 * light + 5], -1)
    img[body] = apple[body]
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.line((240, 110, 252, 60), fill=(90, 60, 30), width=8)
    d.ellipse((255, 50, 330, 95), fill=(90, 170, 70))
    return im.filter(ImageFilter.GaussianBlur(0.8))


def photo_landscape(size=480):
    """风景照的样子：渐变天空、太阳、远近两层山、水面，加传感器噪点。"""
    rng = np.random.default_rng(7)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    t = y / size
    img = np.stack([255 - 120 * t, 170 + 30 * t, 120 + 110 * t], -1)
    sun = np.exp(-(np.hypot(x - 330, y - 170) / 46) ** 2)
    img += sun[..., None] * np.array([40, 60, 30], np.float32)
    far = y > 250 + 30 * np.sin(x / 50) + 14 * np.sin(x / 17)
    img[far] = np.stack([90 + 0 * x, 110 + 40 * t, 150 - 20 * t], -1)[far]
    near = y > 330 + 40 * np.sin(x / 80 + 1) + 10 * np.sin(x / 23)
    img[near] = np.stack([40 + 30 * t, 90 - 20 * t, 70 - 10 * t], -1)[near]
    img += rng.normal(0, 5, img.shape)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))


def pixel_sprite(size=384):
    """像素画放大 12 倍：32×32 的小怪物。"""
    rows = [
        "................................",
        "..........KKKKKKKKKKKK..........",
        "........KKGGGGGGGGGGGGKK........",
        "......KKGGGGGGGGGGGGGGGGKK......",
        ".....KGGGGGGGGGGGGGGGGGGGGK.....",
        "....KGGGWWWGGGGGGGGGGWWWGGGK....",
        "....KGGWWWWWGGGGGGGGWWWWWGGK....",
        "...KGGGWWKKWGGGGGGGGWWKKWGGGK...",
        "...KGGGWWKKWGGGGGGGGWWKKWGGGK...",
        "...KGGGGWWWGGGGGGGGGGWWWGGGGK...",
        "...KGGGGGGGGGGGGGGGGGGGGGGGGK...",
        "...KGGPPGGGGGKKKKKKGGGGGPPGGK...",
        "...KGGPPGGGGKRRRRRRKGGGGPPGGK...",
        "....KGGGGGGGGKRRRRKGGGGGGGGK....",
        "....KGGGGGGGGGKKKKGGGGGGGGGK....",
        ".....KGGGGGGGGGGGGGGGGGGGGK.....",
        "......KKGGGGGGGGGGGGGGGGKK......",
        "........KKGGGGGGGGGGGGKK........",
        ".......KDDKKKKKKKKKKKKDDK.......",
        "......KDDDDK........KDDDDK......",
        "......KKKKKK........KKKKKK......",
    ]
    col = {"K": INK, "G": (120, 200, 120), "W": (255, 255, 255), "P": (255, 170, 180),
           "R": (200, 60, 80), "D": (70, 140, 80)}
    h = len(rows)
    im = Image.new("RGB", (32, 32), (240, 240, 250))
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            if ch in col:
                im.putpixel((c, r + (32 - h) // 2), col[ch])
    return im.resize((size, size), Image.NEAREST)


IMAGES = {
    "flat_no_outline.png": flat_no_outline, "flat_thin_lineart.png": flat_thin_lineart,
    "flat_chibi_face.png": flat_chibi_face, "flat_logo_text.png": flat_logo_text,
    "flat_lowres.png": flat_lowres, "flat_jpeg.jpg": flat_jpeg,
    "soft_shaded.png": soft_shaded, "photo_landscape.png": photo_landscape,
    "pixel_sprite.png": pixel_sprite,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in IMAGES.items():
        im = fn()
        if name.endswith(".jpg"):
            im.save(OUT / name, quality=72)
        else:
            im.save(OUT / name, optimize=True)
        print(name, im.size, (OUT / name).stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
