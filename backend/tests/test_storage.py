import pytest
from sqlalchemy import func, select

from app.models import Palette, PaletteColor
from app.services.palettes import load_core_palette, seed_palettes
from app.services.storage import LocalStorage


def test_save_returns_relative_path_with_two_level_sharding(tmp_path):
    s = LocalStorage(tmp_path)
    rel = s.save("uploads", "abcdef123456", b"hello", ".png")
    assert rel == "uploads/ab/abcdef123456.png"
    assert (tmp_path / rel).read_bytes() == b"hello"


def test_load_and_exists_and_delete(tmp_path):
    s = LocalStorage(tmp_path)
    rel = s.save("exports", "k1", b"data", ".pdf")
    assert s.exists(rel) and s.load(rel) == b"data"
    s.delete(rel)
    assert not s.exists(rel)


def test_load_missing_raises(tmp_path):
    s = LocalStorage(tmp_path)
    with pytest.raises(FileNotFoundError):
        s.load("uploads/xx/nope.png")


def test_path_escape_is_rejected(tmp_path):
    s = LocalStorage(tmp_path)
    with pytest.raises(ValueError):
        s.path("../../etc/passwd")
    with pytest.raises(ValueError):
        s.save("../evil", "k", b"x", ".png")


def test_overwriting_same_key_is_idempotent(tmp_path):
    s = LocalStorage(tmp_path)
    a = s.save("uploads", "same", b"one", ".png")
    b = s.save("uploads", "same", b"two", ".png")
    assert a == b and s.load(a) == b"two"


def test_seed_palettes_inserts_mard_once(db):
    n = seed_palettes(db)
    assert n >= 291
    assert db.scalar(select(func.count()).select_from(Palette)) == 1
    assert db.scalar(select(func.count()).select_from(PaletteColor)) == n
    assert seed_palettes(db) == 0            # 第二次是幂等的
    assert db.scalar(select(func.count()).select_from(PaletteColor)) == n


def test_seeded_colors_carry_provenance(db):
    seed_palettes(db)
    a1 = db.scalars(select(PaletteColor).where(PaletteColor.code == "A1")).one()
    assert a1.rgb.startswith("#") and len(a1.lab) == 3
    assert a1.source in {"beadcolors", "zippland"}
    assert a1.confidence in {"agree", "conflict", "beadcolors_only", "zippland_only"}
    clear = db.scalars(select(PaletteColor).where(PaletteColor.role == "clear")).one()
    assert clear.code == "T1"


def test_load_core_palette_is_cached_and_usable():
    p1 = load_core_palette("mard")
    p2 = load_core_palette("mard")
    assert p1 is p2
    assert len(p1) >= 291 and p1.clear_index is not None
