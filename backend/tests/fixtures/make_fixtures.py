"""生成黄金样本。运行：cd backend && python tests/fixtures/make_fixtures.py"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "images"
OUT.mkdir(exist_ok=True)
rng = np.random.default_rng(42)


def cartoon():           # 粗轮廓平涂：黄脸、黑描边、白眼、红嘴
    im = Image.new("RGB", (400, 400), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse([40, 40, 360, 360], fill=(255, 220, 60), outline=(0, 0, 0), width=12)
    d.ellipse([120, 140, 170, 190], fill=(255, 255, 255), outline=(0, 0, 0), width=8)
    d.ellipse([230, 140, 280, 190], fill=(255, 255, 255), outline=(0, 0, 0), width=8)
    d.ellipse([140, 160, 155, 175], fill=(0, 0, 0))
    d.ellipse([250, 160, 265, 175], fill=(0, 0, 0))
    d.arc([120, 200, 280, 300], 10, 170, fill=(200, 30, 30), width=12)
    im.save(OUT / "cartoon.png")


def logo():              # 少色硬边
    im = Image.new("RGB", (300, 300), (30, 60, 200))
    d = ImageDraw.Draw(im)
    d.rectangle([60, 60, 240, 240], fill=(255, 255, 255))
    d.polygon([(150, 90), (210, 210), (90, 210)], fill=(220, 40, 40))
    im.save(OUT / "logo.png")


def photo_like():        # 渐变 + 噪声 + 一个高光点（合法孤点）
    y, x = np.mgrid[0:300, 0:300]
    r = 120 + 100 * np.sin(x / 60) + rng.normal(0, 8, (300, 300))
    g = 90 + 80 * np.cos(y / 70) + rng.normal(0, 8, (300, 300))
    b = 60 + 60 * (x + y) / 600 + rng.normal(0, 8, (300, 300))
    arr = np.clip(np.stack([r, g, b], -1), 0, 255).astype(np.uint8)
    arr[150:153, 150:153] = 255
    Image.fromarray(arr).save(OUT / "photo_like.png")


def pixel_art():         # 16×16 像素图放大 12×
    small = rng.integers(0, 4, (16, 16))
    colors = np.array([[255, 255, 255], [0, 0, 0], [255, 0, 0], [0, 120, 255]], np.uint8)
    Image.fromarray(colors[small]).resize((192, 192), Image.NEAREST).save(OUT / "pixel_art.png")


def diagonal_trap():     # 一条斜线：直接像素化必出对角虚连
    im = Image.new("RGB", (240, 240), (255, 255, 255))
    ImageDraw.Draw(im).line([10, 230, 230, 10], fill=(0, 0, 0), width=5)
    im.save(OUT / "diagonal_trap.png")


def solid_block():       # 投诉"纯色块被吃只剩轮廓"
    im = Image.new("RGB", (300, 300), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([50, 50, 250, 250], fill=(40, 170, 90), outline=(0, 0, 0), width=6)
    im.save(OUT / "solid_block.png")


def gray_object():       # 投诉"灰色识别成紫色"
    im = Image.new("RGB", (300, 300), (255, 255, 255))
    ImageDraw.Draw(im).rounded_rectangle([60, 100, 240, 200], 20, fill=(128, 128, 128))
    im.save(OUT / "gray_object.png")


def yellow_object():     # 投诉"鹅黄识别成绿"
    im = Image.new("RGB", (300, 300), (255, 255, 255))
    ImageDraw.Draw(im).ellipse([60, 60, 240, 240], fill=(250, 235, 120))
    im.save(OUT / "yellow_object.png")


def transparent_png():   # 投诉"透明变黑/变白"
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([40, 40, 160, 160], fill=(200, 60, 60, 255))
    im.save(OUT / "transparent.png")


def wide_image():        # 投诉"非方图被拉伸"
    im = Image.new("RGB", (600, 200), (255, 255, 255))
    ImageDraw.Draw(im).ellipse([50, 50, 550, 150], fill=(60, 60, 220))
    im.save(OUT / "wide.png")


def thin_diagonal():
    """透明底 + 细斜线 + 一个离群小块。

    其余样本都是不透明白底，整张图每个格子都填满，形状上毫无破绽——
    可拼性检查（孤立豆/对角虚连/不连通/空洞）考察的是填充区域的**形状**，
    实心矩形永远触发不了。真实拼豆图纸是透明底的，这张才是那个形态。
    """
    im = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.line([20, 220, 220, 20], fill=(20, 20, 20, 255), width=4)
    d.ellipse([30, 30, 70, 70], fill=(220, 40, 40, 255))      # 离主体较远 → 不连通
    im.save(OUT / "thin_diagonal.png")


if __name__ == "__main__":
    for fn in (cartoon, logo, photo_like, pixel_art, diagonal_trap,
               solid_block, gray_object, yellow_object, transparent_png, wide_image,
               thin_diagonal):
        fn()
    print("fixtures written to", OUT)
