import io
import uuid
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from app.models import AiRender, Job, Pattern, StylePreset, User
from app.services import jobs as jsvc
from app.services import patterns as psvc
from app.services import quota
from app.services import renders as rsvc

FIXTURES = Path(__file__).parent / "fixtures" / "images"


@pytest.fixture
def user(db):
    u = User(username="job-user", password_hash="x", ai_quota=3)
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def preset(db):
    sp = StylePreset(name="Q版", prompt="粗轮廓 纯色平涂 无渐变 纯色背景", params={})
    db.add(sp)
    db.flush()
    return sp


@pytest.fixture
def project(db, user):
    return psvc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())


# ---------- 缓存键 ----------

def test_input_hash_is_stable_and_sensitive():
    a = rsvc.input_hash(b"img", "p", {"x": 1})
    assert a == rsvc.input_hash(b"img", "p", {"x": 1})
    assert a != rsvc.input_hash(b"img2", "p", {"x": 1})
    assert a != rsvc.input_hash(b"img", "p2", {"x": 1})
    assert a != rsvc.input_hash(b"img", "p", {"x": 2})


def test_input_hash_ignores_dict_ordering():
    assert rsvc.input_hash(b"i", "p", {"a": 1, "b": 2}) == rsvc.input_hash(b"i", "p", {"b": 2, "a": 1})


# ---------- 重绘与额度 ----------

def test_redraw_consumes_quota_and_stores_output(db, user, project, preset):
    before = quota.remaining(db, user.id)
    ar = rsvc.redraw(db, user.id, project, preset)
    assert ar.status == "done" and ar.output_path
    assert psvc.storage_of().exists(ar.output_path)
    assert quota.remaining(db, user.id) == before - 1
    assert Image.open(io.BytesIO(psvc.storage_of().load(ar.output_path))).size[0] > 0


def test_redraw_cache_hit_does_not_consume_quota(db, user, project, preset):
    first = rsvc.redraw(db, user.id, project, preset)
    after_first = quota.remaining(db, user.id)
    second = rsvc.redraw(db, user.id, project, preset)
    assert second.id == first.id
    assert quota.remaining(db, user.id) == after_first


def test_redraw_refunds_quota_on_provider_failure(db, user, project, preset, monkeypatch):
    from app.providers.fake import FakeProvider
    monkeypatch.setattr(rsvc, "_provider_for", lambda name: FakeProvider(fail_times=99))
    before = quota.remaining(db, user.id)
    with pytest.raises(Exception):
        rsvc.redraw(db, user.id, project, preset)
    assert quota.remaining(db, user.id) == before
    failed = db.scalars(select(AiRender).where(AiRender.project_id == project.id)).all()
    assert failed and failed[-1].status == "failed" and failed[-1].error


def test_redraw_without_quota_raises_before_calling_provider(db, project, preset):
    poor = User(username="poor", password_hash="x", ai_quota=0)
    db.add(poor)
    db.flush()
    with pytest.raises(quota.QuotaExceeded):
        rsvc.redraw(db, poor.id, project, preset)


# ---------- 队列 ----------

def test_enqueue_and_claim(db, project):
    j = jsvc.enqueue(db, jsvc.JOB_GENERATE, {"project_id": str(project.id)})
    assert j.status == "pending" and j.attempts == 0
    got = jsvc.claim(db)
    assert got is not None and got.id == j.id
    assert got.status == "running" and got.attempts == 1 and got.locked_at is not None


def test_claim_returns_none_when_empty(db):
    assert jsvc.claim(db) is None


def test_claim_skips_locked_rows(session_factory):
    """两个真实连接同时抢：SKIP LOCKED 必须让它们拿到不同的任务，且都不阻塞。"""
    s1, s2 = session_factory(), session_factory()
    try:
        a = jsvc.enqueue(s1, jsvc.JOB_GENERATE, {"n": 1})
        b = jsvc.enqueue(s1, jsvc.JOB_GENERATE, {"n": 2})
        s1.commit()
        first = jsvc.claim(s1)          # s1 持有行锁，未提交
        second = jsvc.claim(s2)         # s2 必须跳过被锁那行，拿到另一条
        assert first is not None and second is not None
        assert first.id != second.id
        assert {first.id, second.id} == {a.id, b.id}
    finally:
        s1.rollback()
        s2.rollback()
        c = session_factory()
        c.query(Job).delete()
        c.commit()
        for s in (s1, s2, c):
            s.close()


@pytest.fixture
def committed(session_factory):
    """真实提交的会话 + 数据。

    run_generate_job 内部自己开新连接，而 `db` 夹具的 commit 只提交 SAVEPOINT，
    数据对别的连接不可见——所以这类测试必须全程用真实会话，自己负责清理。
    """
    from app.models import Project

    s = session_factory()
    u = User(username=f"committed-{uuid.uuid4().hex[:8]}", password_hash="x", ai_quota=3)
    s.add(u)
    s.commit()
    proj = psvc.create_project(s, u.id, "t", (FIXTURES / "logo.png").read_bytes())
    s.commit()
    try:
        yield s, u, proj
    finally:
        s.rollback()
        c = session_factory()
        c.query(Job).delete()
        c.query(Pattern).filter(Pattern.project_id == proj.id).delete()
        c.query(Project).filter(Project.id == proj.id).delete()
        c.query(User).filter(User.id == u.id).delete()
        c.commit()
        c.close()
        s.close()


def test_run_generate_job_without_ai_produces_pattern(session_factory, committed):
    s, user, project = committed
    job = jsvc.enqueue(s, jsvc.JOB_GENERATE, {
        "project_id": str(project.id), "user_id": str(user.id),
        "use_ai": False, "params": {"grid_long_side": 20, "max_colors": 4}})
    s.commit()

    jsvc.run_generate_job(session_factory, job.id)

    s.expire_all()
    done = s.get(Job, job.id)
    assert done.status == "done", done.error
    pat = s.get(Pattern, uuid.UUID(done.result["pattern_id"]))
    assert pat is not None and len(pat.grid) == 20


def test_run_generate_job_records_error_on_failure(session_factory, committed):
    s, user, project = committed
    job = jsvc.enqueue(s, jsvc.JOB_GENERATE, {
        "project_id": str(project.id), "user_id": str(user.id),
        "use_ai": False, "params": {"grid_long_side": 99999}})
    s.commit()

    jsvc.run_generate_job(session_factory, job.id)

    s.expire_all()
    failed = s.get(Job, job.id)
    assert failed.status == "failed" and failed.error


def test_run_generate_job_with_ai_refunds_quota_when_provider_fails(session_factory, committed,
                                                                    monkeypatch):
    """AI 炸了必须退额度——job 走的是独立连接，这条路径只能用真实会话测。"""
    from app.providers.fake import FakeProvider
    monkeypatch.setattr(rsvc, "_provider_for", lambda name: FakeProvider(fail_times=99))

    s, user, project = committed
    preset = StylePreset(name="Q版", prompt="粗轮廓", params={})
    s.add(preset)
    s.commit()
    before = quota.remaining(s, user.id)

    job = jsvc.enqueue(s, jsvc.JOB_GENERATE, {
        "project_id": str(project.id), "user_id": str(user.id), "use_ai": True,
        "style_preset_id": str(preset.id), "params": {"grid_long_side": 20}})
    s.commit()

    jsvc.run_generate_job(session_factory, job.id)

    s.expire_all()
    assert s.get(Job, job.id).status == "failed"
    assert quota.remaining(s, user.id) == before
    s.query(AiRender).filter(AiRender.project_id == project.id).delete()
    s.query(StylePreset).filter(StylePreset.id == preset.id).delete()
    s.commit()


def test_reclaim_stale_marks_running_jobs_failed_and_refunds(db, user, project):
    j = jsvc.enqueue(db, jsvc.JOB_GENERATE, {
        "project_id": str(project.id), "user_id": str(user.id), "use_ai": True})
    quota.reserve(db, user.id)
    before = quota.remaining(db, user.id)
    j.status = "running"
    db.flush()
    n = jsvc.reclaim_stale(db)
    assert n == 1
    assert db.get(Job, j.id).status == "failed"
    assert quota.remaining(db, user.id) == before + 1     # 退还了
