"""给还原度上线之前生成的图纸补上还原度（只填 fidelity 为空的行，不动图纸内容）。

    python scripts/backfill_fidelity.py          # 只补没有分数的
    python scripts/backfill_fidelity.py --all    # 全部重算（还原度的算法改了以后用）

注意：补的是"这张旧图纸对着原图有多像"，不会重新出图——旧算法出的图纸（比如描边断口的）
分数会如实偏低，重新出一次图才会用上新算法。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal  # noqa: E402
from app.models import Pattern  # noqa: E402
from app.services import patterns as psvc  # noqa: E402
from app.services.palettes import load_core_palette  # noqa: E402


def main() -> None:
    done = skipped = 0
    with SessionLocal() as db:
        redo = "--all" in sys.argv
        for pat in db.query(Pattern).all():
            if pat.fidelity and not redo:
                continue
            params = psvc.params_from_dict(pat.params or {})
            palette = load_core_palette(params.palette_id)
            fid = psvc._fidelity_of(db, pat, psvc.grid_from_db(pat.grid), palette, params)
            if fid is None:
                skipped += 1
                continue
            pat.fidelity = fid
            done += 1
        db.commit()
    print(f"回填 {done} 张图纸，{skipped} 张算不了（原图读不出来等）")


if __name__ == "__main__":
    main()
