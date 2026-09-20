from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Job, Project, StylePreset
from app.services import patterns as psvc
from app.services import quota, renders

JOB_GENERATE = "generate"


def enqueue(db: Session, type: str, payload: dict) -> Job:
    job = Job(type=type, payload=payload, status="pending")
    db.add(job)
    db.flush()
    return job


def claim(db: Session) -> Job | None:
    """SKIP LOCKED 取一条待办。两个消费者并发调用不会拿到同一条，也不会互相阻塞。"""
    job = db.scalar(
        select(Job).where(Job.status == "pending").order_by(Job.created_at)
        .with_for_update(skip_locked=True).limit(1))
    if job is None:
        return None
    job.status = "running"
    job.locked_at = datetime.now(timezone.utc)
    job.attempts += 1
    db.flush()
    return job


def run_generate_job(session_factory: sessionmaker, job_id: int) -> None:
    """在独立事务里执行一个生成任务。异常只落库，不外抛——调用方是后台任务。"""
    db: Session = session_factory()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = "running"
        job.locked_at = datetime.now(timezone.utc)
        job.attempts += 1
        db.commit()

        payload = job.payload or {}
        project = db.get(Project, uuid.UUID(payload["project_id"]))
        if project is None:
            raise LookupError(f"project {payload.get('project_id')} 不存在")
        user_id = uuid.UUID(payload["user_id"])
        params = psvc.params_from_dict(payload.get("params") or {})

        ai_render = None
        if payload.get("use_ai"):
            preset_id = payload.get("style_preset_id")
            preset = db.get(StylePreset, uuid.UUID(preset_id)) if preset_id else None
            if preset is None:
                raise LookupError("use_ai=true 但未指定有效的 style_preset_id")
            ai_render = renders.redraw(db, user_id, project, preset, payload.get("provider"))

        pattern = psvc.generate(db, project, params, ai_render)
        job.result = {"pattern_id": str(pattern.id),
                      "ai_render_id": str(ai_render.id) if ai_render else None}
        job.status = "done"
        job.error = None
        db.commit()
    except Exception as e:                      # noqa: BLE001 — 后台任务必须吞异常并落库
        db.rollback()
        job = db.get(Job, job_id)
        if job is not None:
            job.status = "failed"
            job.error = f"{type(e).__name__}: {e}"[:2000]
            db.commit()
    finally:
        db.close()


def reclaim_stale(db: Session) -> int:
    """启动钩子：进程重启会丢掉进行中的任务，把它们标失败并退还已扣的 AI 额度。"""
    stale = db.scalars(select(Job).where(Job.status == "running")).all()
    for job in stale:
        job.status = "failed"
        job.error = "服务重启，任务中断"
        payload = job.payload or {}
        if payload.get("use_ai") and payload.get("user_id"):
            try:
                quota.refund(db, uuid.UUID(payload["user_id"]))
            except LookupError:
                pass
    db.flush()
    return len(stale)
