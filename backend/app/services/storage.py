from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import get_settings

_SAFE = re.compile(r"^[A-Za-z0-9_\-]+$")


class Storage(Protocol):
    def save(self, category: str, key: str, data: bytes, ext: str) -> str: ...
    def load(self, rel_path: str) -> bytes: ...
    def path(self, rel_path: str) -> Path: ...
    def exists(self, rel_path: str) -> bool: ...
    def delete(self, rel_path: str) -> None: ...


class LocalStorage:
    """落盘布局 <root>/<category>/<key 前两位>/<key><ext>。两级散列避免单目录堆几万文件。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _rel(self, category: str, key: str, ext: str) -> str:
        if not _SAFE.match(category) or not _SAFE.match(key):
            raise ValueError(f"unsafe category/key: {category!r}/{key!r}")
        if not ext.startswith(".") or not _SAFE.match(ext[1:]):
            raise ValueError(f"unsafe ext: {ext!r}")
        return f"{category}/{key[:2]}/{key}{ext}"

    def path(self, rel_path: str) -> Path:
        p = (self.root / rel_path).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError(f"path escapes storage root: {rel_path!r}")
        return p

    def save(self, category: str, key: str, data: bytes, ext: str) -> str:
        rel = self._rel(category, key, ext)
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)          # 原子替换，避免半截文件被读到
        return rel

    def load(self, rel_path: str) -> bytes:
        p = self.path(rel_path)
        if not p.exists():
            raise FileNotFoundError(rel_path)
        return p.read_bytes()

    def exists(self, rel_path: str) -> bool:
        return self.path(rel_path).exists()

    def delete(self, rel_path: str) -> None:
        self.path(rel_path).unlink(missing_ok=True)


@lru_cache
def get_storage() -> Storage:
    return LocalStorage(get_settings().data_dir)
