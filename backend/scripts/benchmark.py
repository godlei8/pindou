"""对全部黄金样本跑流水线，打印量化指标表。

用法：cd backend && python scripts/benchmark.py [--smoothness 1.5]
λ=0 的一列等价于市面工具的"逐格最近色"行为，是天然对照组。
"""
import argparse
import time
from pathlib import Path

from app.core import pipeline
from app.core.palette import Palette
from app.core.types import Params

IMG = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "images"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoothness", type=float, default=1.0)
    ap.add_argument("--colors", type=int, default=12)
    ap.add_argument("--size", type=int, default=50)
    a = ap.parse_args()
    palette = Palette.load("mard")
    print(f"λ={a.smoothness}  colors<={a.colors}  size={a.size}")
    print(f"{'image':<20}{'kind':<10}{'ms':>7}{'colors':>8}{'conf%':>8}{'comps':>7}{'thin':>7}{'score':>7}")
    for p in sorted(IMG.glob("*.png")):
        t = time.perf_counter()
        res = pipeline.run(p.read_bytes(),
                           Params(grid_long_side=a.size, max_colors=a.colors,
                                  smoothness=a.smoothness), palette)
        ms = (time.perf_counter() - t) * 1000
        r = res.report
        print(f"{p.name:<20}{res.input_kind:<10}{ms:>7.0f}{len(res.working_palette):>8}"
              f"{r.confetti_pct:>8.2f}{r.n_components:>7}{r.metrics['thin_ratio']:>7.2f}{r.score:>7.1f}")


if __name__ == "__main__":
    main()
