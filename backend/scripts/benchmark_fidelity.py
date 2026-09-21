"""批量出图，看各类图的还原度 / 可拼性 / 色数 / 用时，并拼一张「原图 | 图纸」对照图。

    python scripts/benchmark_fidelity.py [--sheet 对照图.png] [--local] [--grid 58]

--local：把本机 data/uploads 里上传过的图也一起测（真人照片只在本机看，不进仓库）。
还原度第一：改算法前后各跑一遍，任何一张图的还原度都不应该下降。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.core import pipeline  # noqa: E402
from app.core.palette import Palette  # noqa: E402
from app.core.types import EMPTY, Params  # noqa: E402

BENCH = ROOT / "tests" / "fixtures" / "bench"
SAMPLES = ROOT.parent / "frontend" / "public" / "samples"
FIXTURES = ROOT / "tests" / "fixtures" / "images"


def collect(local: bool) -> list[Path]:
    files = sorted(SAMPLES.glob("*.png")) + sorted(BENCH.glob("*.*"))
    files += [FIXTURES / n for n in ("cartoon.png", "photo_like.png")]
    if local:
        seen = set()
        for f in sorted((ROOT / "data" / "uploads").rglob("*.*")):
            try:
                with Image.open(f) as im:
                    if min(im.size) < 300:
                        continue
                    key = (im.size, f.stat().st_size)
            except Exception:
                continue
            if key not in seen:
                seen.add(key)
                files.append(f)
    return [f for f in files if f.exists()]


def render(grid: np.ndarray, palette: Palette, px: int) -> Image.Image:
    rgb = np.full((*grid.shape, 3), 255, np.uint8)
    on = grid != EMPTY
    rgb[on] = palette.rgb[grid[on]]
    return Image.fromarray(rgb).resize((grid.shape[1] * px, grid.shape[0] * px), Image.NEAREST)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--grid", type=int, nargs="*", default=[58])
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    pal = Palette.load("mard")
    rows = []
    print(f"{'图':28s} {'格':>3s} {'方法':>5s} {'还原度':>6s} {'平均ΔE':>6s} {'最差ΔE':>6s} {'可拼':>5s} {'散点%':>5s} {'色':>3s} {'秒':>5s}")
    for f in collect(args.local):
        if args.only and args.only not in f.name:
            continue
        name = f.name if f.parent.name != "uploads" and "uploads" not in f.parts else f"(本机){f.name[:10]}"
        for n in args.grid:
            t = time.time()
            res = pipeline.run(f.read_bytes(), Params(grid_long_side=n, remove_background=True), pal)
            dt = time.time() - t
            fid = res.fidelity or {}
            rep = res.report
            print(f"{name:28s} {n:3d} {fid.get('method', '-'):>5s} {fid.get('score', 0):6.1f} "
                  f"{fid.get('mean_delta_e', 0):6.2f} {fid.get('worst_delta_e', 0):6.2f} "
                  f"{rep.score if rep else 0:5.1f} {rep.confetti_pct if rep else 0:5.1f} "
                  f"{len(res.color_stats):3d} {dt:5.2f}")
            rows.append((f, res))
    if args.sheet and rows:
        cell = 360
        sheet = Image.new("RGB", (cell * 2 + 30, (cell + 10) * len(rows) + 10), (255, 255, 255))
        for i, (f, res) in enumerate(rows):
            src = Image.open(f).convert("RGBA")
            bg = Image.new("RGBA", src.size, (255, 255, 255, 255))
            src = Image.alpha_composite(bg, src).convert("RGB")
            src.thumbnail((cell, cell))
            px = max(1, cell // max(res.grid.shape))
            sheet.paste(src, (10, 10 + i * (cell + 10)))
            sheet.paste(render(res.grid, pal, px), (cell + 20, 10 + i * (cell + 10)))
        sheet.save(args.sheet)
        print("对照图：", args.sheet)


if __name__ == "__main__":
    main()
