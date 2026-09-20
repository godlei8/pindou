import json
from pathlib import Path

import numpy as np

from app.core.palette import Palette, normalize_code
from app.palettes.build_mard import merge_sources

MARD_JSON = Path(__file__).resolve().parents[1] / "app" / "palettes" / "mard.json"


def test_normalize_code():
    assert normalize_code("A01") == "A1"
    assert normalize_code("A1") == "A1"
    assert normalize_code("ZG01") == "ZG1"
    assert normalize_code("h10") == "H10"
    assert normalize_code(" T01 ") == "T1"


def test_merge_sources_marks_agreement_and_conflict():
    bead = {"A1": (249, 240, 205), "H1": (226, 226, 226), "X9": (1, 2, 3), "T1": (226, 223, 215)}
    zipp = {"A1": "#FAF4C8", "H1": "#FDFBFF", "Y7": "#000000", "T1": "#FFFFFF"}
    colors = {c["code"]: c for c in merge_sources(bead, zipp, tolerance_de=3.0)}
    assert colors["A1"]["confidence"] == "agree"
    assert colors["H1"]["confidence"] == "conflict"
    assert colors["H1"]["alt_hex"] == "#FDFBFF"
    assert colors["X9"]["confidence"] == "beadcolors_only"
    assert colors["Y7"]["confidence"] == "zippland_only"
    assert colors["T1"]["role"] == "clear"


def test_mard_json_exists_and_is_complete():
    data = json.loads(MARD_JSON.read_text(encoding="utf-8"))
    codes = [c["code"] for c in data["colors"]]
    assert len(codes) >= 291
    assert len(set(codes)) == len(codes)
    assert all(c["source"] for c in data["colors"])
    assert any(c.get("role") == "clear" for c in data["colors"])
    for c in data["colors"]:
        assert c["hex"].startswith("#") and len(c["hex"]) == 7
        int(c["hex"][1:], 16)   # 必须是合法十六进制——防 #FECODF 这种字母 O


def test_palette_load_and_nearest():
    p = Palette.load("mard")
    assert len(p) >= 291
    assert p.lab.shape == (len(p), 3) and p.oklab.shape == (len(p), 3)
    assert p.clear_index is not None and p.codes[p.clear_index] == "T1"
    i = p.index_of("A01")
    assert p.codes[i] == "A1"
    assert p.nearest(p.lab[[i]])[0] == i
    black = np.array([[0.0, 0.0, 0.0]])
    j = p.nearest(black)[0]
    assert p.lab[j, 0] < 20
