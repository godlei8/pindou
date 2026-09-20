"""从两个开源来源构建 mard.json，交叉校验。

用法：cd backend && python -m app.palettes.build_mard
来源①（主）: maxcleme/beadcolors raw/mard.csv   格式 code,code,r,g,b,source
来源②（校验）: Zippland/perler-beads colorSystemMapping.json  {"#HEX": {"MARD": "A01", ...}}
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np

from app.core.color import delta_e_2000, srgb_to_lab

URL_BEADCOLORS = "https://raw.githubusercontent.com/maxcleme/beadcolors/master/raw/mard.csv"
URL_ZIPPLAND = "https://raw.githubusercontent.com/Zippland/perler-beads/master/src/app/colorSystemMapping.json"
OUT = Path(__file__).with_name("mard.json")
CLEAR_CODES = {"T1"}

_CODE_RE = re.compile(r"^([A-Za-z]+)0*(\d+)$")


def normalize_code(code: str) -> str:
    m = _CODE_RE.match(code.strip())
    if not m:
        raise ValueError(f"bad color code: {code!r}")
    return f"{m.group(1).upper()}{int(m.group(2))}"


def _sort_key(code: str):
    m = _CODE_RE.match(code)
    return (m.group(1), int(m.group(2)))


def _hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _rgb(hex_: str):
    h = hex_.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def parse_beadcolors(text: str) -> dict:
    out = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 5:
            continue
        out[normalize_code(row[0])] = (int(row[2]), int(row[3]), int(row[4]))
    return out


def parse_zippland(text: str) -> dict:
    out = {}
    for hex_, brands in json.loads(text).items():
        if "MARD" in brands:
            out[normalize_code(brands["MARD"])] = hex_.upper()
    return out


def merge_sources(bead: dict, zipp: dict, tolerance_de: float = 3.0) -> list[dict]:
    colors = []
    for code in sorted(set(bead) | set(zipp), key=_sort_key):
        entry = {"code": code, "name": code}
        if code in bead and code in zipp:
            rgb_b, rgb_z = bead[code], _rgb(zipp[code])
            de = float(delta_e_2000(srgb_to_lab(np.array(rgb_b) / 255.0),
                                    srgb_to_lab(np.array(rgb_z) / 255.0)))
            entry.update(hex=_hex(rgb_b), source="beadcolors", alt_hex=zipp[code],
                         delta_e_between_sources=round(de, 2),
                         confidence="agree" if de <= tolerance_de else "conflict")
        elif code in bead:
            entry.update(hex=_hex(bead[code]), source="beadcolors", confidence="beadcolors_only")
        else:
            entry.update(hex=zipp[code], source="zippland", confidence="zippland_only")
        if code in CLEAR_CODES:
            entry["role"] = "clear"
        colors.append(entry)
    return colors


def main() -> int:
    bead = parse_beadcolors(urllib.request.urlopen(URL_BEADCOLORS, timeout=30).read().decode("utf-8"))
    zipp = parse_zippland(urllib.request.urlopen(URL_ZIPPLAND, timeout=30).read().decode("utf-8"))
    colors = merge_sources(bead, zipp)
    doc = {"id": "mard", "brand": "MARD", "version": str(date.today()),
           "sources": {"beadcolors": URL_BEADCOLORS, "zippland": URL_ZIPPLAND},
           "colors": colors}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    n_conf = sum(c["confidence"] == "conflict" for c in colors)
    print(f"wrote {OUT} with {len(colors)} colors, {n_conf} conflicts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
