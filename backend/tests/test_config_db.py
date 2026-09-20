import pytest
from sqlalchemy import text

from app.config import Settings, get_settings
from app.db import SessionLocal, engine


def test_settings_load_from_env():
    s = get_settings()
    assert s.database_url.startswith("postgresql+psycopg://")
    assert len(s.session_secret) >= 16
    assert s.bcrypt_rounds >= 4


def test_settings_is_cached():
    assert get_settings() is get_settings()


def test_data_dir_is_created(tmp_path):
    s = Settings(database_url="postgresql+psycopg://a:b@h/d", session_secret="x" * 16,
                 data_dir=tmp_path / "nested" / "data")
    assert s.data_dir.exists() and s.data_dir.is_dir()


def test_can_connect_to_test_database(db):
    assert db.execute(text("select 1")).scalar() == 1


def test_db_fixture_rolls_back_between_tests(db):
    db.execute(text("create temporary table t_probe (id int)"))
    db.execute(text("insert into t_probe values (1)"))
    assert db.execute(text("select count(*) from t_probe")).scalar() == 1
