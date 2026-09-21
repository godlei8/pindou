"""给人脸检测上线之前生成的图纸补上人脸信息（只填 faces 为空的行，不动图纸内容）。

    python scripts/backfill_faces.py

旧图纸没有 faces，打开时就不会出现"脸太小"的提示，得改一下参数重算才有。
这里对每张图纸所用的那张图（原图或 AI 重绘图）检测一次、回填。
同一张图只检测一次；检测不到脸的写成空列表，表示"查过了、没有"。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import face, image_io  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import AiRender, Pattern, Project  # noqa: E402
from app.services.storage import get_storage  # noqa: E402


def main() -> None:
    st = get_storage()
    cache: dict[str, list] = {}
    done = found = 0
    with SessionLocal() as db:
        for pat in db.query(Pattern).filter(Pattern.faces.is_(None)).all():
            if pat.ai_render_id:
                r = db.get(AiRender, pat.ai_render_id)
                path = r.output_path if r else None
            else:
                path = db.get(Project, pat.project_id).source_image_path
            if not path:
                continue
            if path not in cache:
                try:
                    cache[path] = [f.to_dict() for f in face.detect_faces(image_io.load_rgba(st.load(path)))]
                except Exception as e:                      # 图读不出来就跳过，别中断整批
                    print(f"跳过 {pat.id}: {e}")
                    continue
            pat.faces = cache[path]
            done += 1
            found += bool(pat.faces)
        db.commit()
    print(f"回填 {done} 张图纸，其中 {found} 张检测到人脸（共检测了 {len(cache)} 张不同的图）")


if __name__ == "__main__":
    main()
