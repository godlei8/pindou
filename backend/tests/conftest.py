import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models import Base


@pytest.fixture
def rng():
    return np.random.default_rng(0)


@pytest.fixture(scope="session")
def settings():
    s = get_settings()
    if not s.test_database_url:
        pytest.skip("TEST_DATABASE_URL not set — see plan 前置条件")
    return s


@pytest.fixture(scope="session")
def test_engine(settings):
    eng = create_engine(settings.test_database_url, pool_pre_ping=True, future=True)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(test_engine):
    """每个测试跑在一个外层事务里，结束回滚——测试之间互不影响，也不用重建表。"""
    conn = test_engine.connect()
    trans = conn.begin()
    session = sessionmaker(bind=conn, autoflush=False, expire_on_commit=False, future=True)()
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def session_factory(test_engine):
    """需要真实提交的场景（如 SKIP LOCKED 并发测试）用它，自己负责清理。"""
    return sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False, future=True)
