from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core.color import pairwise_delta_e, srgb_to_lab, srgb_to_oklab
from app.palettes.build_mard import normalize_code

__all__ = ["Palette", "normalize_code"]

_PALETTE_DIR = Path(__file__).resolve().parents[1] / "palettes"


@dataclass
class Palette:
    id: str
    codes: list[str]
    names: list[str]
    rgb: np.ndarray
    lab: np.ndarray
    oklab: np.ndarray
    roles: dict[str, str]
    sources: list[str]
    confidence: list[str]

    @classmethod
    def load(cls, palette_id: str = "mard") -> "Palette":
        doc = json.loads((_PALETTE_DIR / f"{palette_id}.json").read_text(encoding="utf-8"))
        colors = doc["colors"]
        rgb = np.array([[int(c["hex"][i:i + 2], 16) for i in (1, 3, 5)] for c in colors], dtype=np.uint8)
        rgb01 = rgb / 255.0
        return cls(
            id=doc["id"],
            codes=[c["code"] for c in colors],
            names=[c.get("name", c["code"]) for c in colors],
            rgb=rgb,
            lab=srgb_to_lab(rgb01),
            oklab=srgb_to_oklab(rgb01),
            roles={c["code"]: c["role"] for c in colors if "role" in c},
            sources=[c["source"] for c in colors],
            confidence=[c["confidence"] for c in colors],
        )

    def __len__(self) -> int:
        return len(self.codes)

    def index_of(self, code: str) -> int:
        return self.codes.index(normalize_code(code))

    @property
    def clear_index(self) -> int | None:
        for code, role in self.roles.items():
            if role == "clear":
                return self.codes.index(code)
        return None

    def nearest(self, lab: np.ndarray) -> np.ndarray:
        return pairwise_delta_e(np.atleast_2d(lab), self.lab).argmin(axis=1)
