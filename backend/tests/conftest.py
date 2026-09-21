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
        # 触发过 IntegrityError 的测试里，事务已被解绑；再 rollback 会发 SAWarning。
        if trans.is_active:
            trans.rollback()
        conn.close()


@pytest.fixture
def session_factory(test_engine):
    """需要真实提交的场景（如 SKIP LOCKED 并发测试）用它，自己负责清理。"""
    return sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False, future=True)


@pytest.fixture
def client(db):
    """TestClient，路由内的 get_db 被换成测试事务里的同一个 session。"""
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import create_app

    app = create_app(run_startup=False)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client, db):
    """已登录的客户端，附带 user 属性。"""
    from sqlalchemy import select

    from app.models import InviteCode, User
    from app.services import auth as auth_svc

    original_rounds = auth_svc._ROUNDS
    auth_svc._ROUNDS = 4
    try:
        db.add(InviteCode(code="FIXTURE", max_uses=99))
        db.flush()
        client.post("/api/auth/register",
                    json={"username": "fixture-user", "password": "pw12345678",
                          "invite_code": "FIXTURE"})
        client.user = db.scalar(select(User).where(User.username == "fixture-user"))
        client.user.ai_quota = 10
        db.flush()
        yield client
    finally:
        auth_svc._ROUNDS = original_rounds


@pytest.fixture
def invite_other(db):
    from app.models import InviteCode
    db.add(InviteCode(code="OTHER", max_uses=9))
    db.flush()


@pytest.fixture(autouse=True)
def _no_real_ai_provider(monkeypatch):
    """测试一律用假 provider。

    否则 redraw 会读 providers.yaml + .env 里的真 key 去调百炼，每跑一次测试就扣一次钱
    （测试事务回滚，库里还看不到记录）。个别测试自己再 monkeypatch 会覆盖这里。
    """
    from app.providers.fake import FakeProvider
    from app.services import renders

    monkeypatch.setattr(renders, "_provider_for", lambda name: FakeProvider())
