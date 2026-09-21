"""生成网站图标：「馨豆」——一颗顶着豆芽的胖红豆。

16×16 真像素画，配色全部取 MARD 真实色号（和 docs/DESIGN.md 的色板一致）。
输出到 frontend/public/：
  favicon.svg          浏览器标签页（矢量，任意缩放都是清晰方格）
  favicon.ico          老浏览器兜底（16/32/48）
  apple-touch-icon.png iOS 加到主屏幕（180，米黄底板）
  icon-192.png / icon-512.png  Android / PWA

改图就改下面的 SPRITE，再跑：python scripts/make_favicon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

SPRITE = [
    "................",
    ".....GG..GG.....",
    ".....GGggGG.....",
    ".......gg.......",
    "....KKKKKKKK....",
    "...KRRRRRRRRK...",
    "..KRWWRRRRRRRK..",
    "..KRWRRRRRRRRK..",
    "..KRRKRRRRKRRK..",
    "..KRRKRRRRKRRK..",
    "..KRPPRRRRPPRK..",
    "..KRRRKRRKRRRK..",
    "..KRRRRKKRRRRK..",
    "...KRRRRRRRRK...",
    "....KKKKKKKK....",
    "................",
]

COLORS = {
    "K": "#3B2F23",  # H16 墨
    "R": "#FC3D45",  # F2  豆红
    "W": "#FFFFFF",  # H2  高光
    "P": "#FF9FB0",  # 腮红（只在图标里用）
    "G": "#00BD35",  # B5  叶
    "g": "#009A2B",  # 叶脉，深一点
}
BOARD = "#F9F0CD"    # A1 底板米黄

OUT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def _rgba(hex_: str) -> tuple[int, int, int, int]:
    h = hex_.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255


def sprite_image(bg: str | None = None) -> Image.Image:
    im = Image.new("RGBA", (16, 16), _rgba(bg) if bg else (0, 0, 0, 0))
    for y, row in enumerate(SPRITE):
        assert len(row) == 16, f"第 {y} 行不是 16 格"
        for x, ch in enumerate(row):
            if ch in COLORS:
                im.putpixel((x, y), _rgba(COLORS[ch]))
    return im


def svg() -> str:
    rects = []
    for y, row in enumerate(SPRITE):
        x = 0
        while x < 16:                       # 同色的连续一段合成一个矩形，文件小一点
            ch = row[x]
            end = x
            while end + 1 < 16 and row[end + 1] == ch:
                end += 1
            if ch in COLORS:
                rects.append(f'<rect x="{x}" y="{y}" width="{end - x + 1}" height="1" '
                             f'fill="{COLORS[ch]}"/>')
            x = end + 1
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
            'shape-rendering="crispEdges">' + "".join(rects) + "</svg>\n")


def padded(size: int, pad_ratio: float = 0.125) -> Image.Image:
    """主屏图标：米黄底板 + 居中放大的像素画（整数倍放大，保持方格）。"""
    canvas = Image.new("RGBA", (size, size), _rgba(BOARD))
    scale = int(size * (1 - 2 * pad_ratio)) // 16
    art = sprite_image().resize((16 * scale, 16 * scale), Image.NEAREST)
    off = (size - 16 * scale) // 2
    canvas.alpha_composite(art, (off, off))
    return canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "favicon.svg").write_text(svg(), encoding="utf-8")
    base = sprite_image()
    base.resize((48, 48), Image.NEAREST).save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    padded(180).convert("RGB").save(OUT / "apple-touch-icon.png")
    padded(192).save(OUT / "icon-192.png")
    padded(512).save(OUT / "icon-512.png")
    print("写入", OUT)


if __name__ == "__main__":
    main()
