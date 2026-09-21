"""生成首页介绍用的示例图纸。

    python scripts/make_intro_example.py

首页介绍不用"三张功能卡片"，而是展示一张**真实的输出**并在上面标注。
所以这张图必须是流水线真跑出来的，不能手画——手画就成了宣传图，说的不是真话。

输出：
- frontend/public/intro/mushroom-source.png  原图（缩小）
- frontend/public/intro/mushroom-sheet.png   下载同款的整张：图纸 + 材料清单
- frontend/src/components/introExample.ts    图的尺寸、标注点位置、真实统计数字
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import pipeline, render  # noqa: E402
from app.core.palette import Palette  # noqa: E402
from app.core.types import Params  # noqa: E402

SRC = ROOT / "frontend" / "public" / "samples" / "mushroom.png"
OUT_DIR = ROOT / "frontend" / "public" / "intro"
TS_OUT = ROOT / "frontend" / "src" / "components" / "introExample.ts"
CELL_PX = 18          # ≥18 才画色号（见 lib/zoom.ts 的 SHOW_CODES_MIN）；24×18 正好放进 480px 的侧栏
GRID = 24
SMOOTHNESS = 4.0
# 参数是挑过的：20 格时轮廓和白点都糊成过渡色（spec §11 记过的已知短板），不适合当示例。
# 24 格 + λ=4 白点是纯白、伞盖整片同色。首页会把这组参数原样标出来，不让人以为默认就这效果。


def main() -> None:
    palette = Palette.load("mard")
    result = pipeline.run(SRC.read_bytes(),
                          Params(grid_long_side=GRID, smoothness=SMOOTHNESS), palette)
    grid = result.grid
    rows, cols = grid.shape

    opts = render.RenderOptions(cell_px=CELL_PX)
    pattern = render.render_grid(grid, palette, opts)
    sheet = render.render_sheet(grid, palette, opts)
    margin = int(CELL_PX * 0.9)          # render_grid 的坐标轴留白

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT_DIR / "mushroom-sheet.png", optimize=True)
    Image.open(SRC).convert("RGB").resize((160, 160), Image.LANCZOS).save(
        OUT_DIR / "mushroom-source.png", optimize=True)

    counts = {int(k): int(v) for k, v in result.color_stats.items()}
    total = sum(counts.values())

    # 标注点：蘑菇盖上一个四邻同色的内部格（它的色号清楚可见，也代表"整片同色"）
    center_col = cols // 2
    cap = int(grid[rows // 4, center_col])
    interior = [(r, c) for r in range(1, rows - 1) for c in range(1, cols - 1)
                if grid[r, c] == cap and all(grid[r + dr, c + dc] == cap
                                             for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
    # 取最靠左上的内部格，离右边的注释远一点，免得标记压住别的色号
    code_cell = min(interior, key=lambda rc: (rc[0] + rc[1]))

    def pct(x: float, total_px: int) -> float:
        return round(x / total_px * 100, 2)

    def cell_center(r: int, c: int) -> dict:
        x = margin + c * CELL_PX + CELL_PX / 2
        y = margin + r * CELL_PX + CELL_PX / 2
        return {"x": pct(x, sheet.width), "y": pct(y, sheet.height)}

    # ② 标在清单标题**后面**的空白处，不能压住标题。位置按 render_legend 的排版规则算：
    #   标题行垂直中心 = 清单顶 + pad + 字号/2，标题宽度用同一个字体量出来
    legend_top = pattern.height + max(8, CELL_PX // 2)
    font_px = 24 if CELL_PX >= 20 else 12            # 与 render_sheet 一致
    lpad = max(8, CELL_PX // 2)
    title = f"材料清单　共 {total} 颗 · {len(counts)} 色"
    title_end = lpad + render.cjk_font(font_px).getlength(title)
    data = {
        "width": sheet.width,
        "height": sheet.height,
        "grid": [rows, cols],
        "smoothness": SMOOTHNESS,
        "capCode": palette.codes[cap],
        "beads": total,
        "colors": len(counts),
        "score": (result.report.score if result.report else None),
        # 只标图上确实成立的事。"边缘干净"这种话这张图撑不住（边上有过渡色），不标。
        "markers": {
            "code": cell_center(*code_cell),
            "legend": {"x": pct(title_end + 10, sheet.width),
                       "y": pct(legend_top + lpad + font_px / 2, sheet.height)},
        },
    }

    TS_OUT.write_text(
        "// 由 backend/scripts/make_intro_example.py 生成，别手改——改了就不是真实输出了。\n"
        f"export const INTRO_EXAMPLE = {json.dumps(data, ensure_ascii=False, indent=2)} as const;\n",
        encoding="utf-8")

    print(json.dumps(data, ensure_ascii=False, indent=2))
    print("色号：", {palette.codes[k]: v for k, v in sorted(counts.items(), key=lambda kv: -kv[1])})


if __name__ == "__main__":
    main()
