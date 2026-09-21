from __future__ import annotations

import uuid

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response,
                     UploadFile, status)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core import pipeline
from app.db import SessionLocal, get_db
from app.models import AiRender, Pattern, Project, StylePreset, User
from app.schemas import (GenerateIn, JobOut, PatternParamsIn, ProjectOut, ProjectRenameIn,
                         SizeSuggestion)
from app.services import jobs as jsvc
from app.services import patterns as psvc
from app.services import quota
from app.services.palettes import load_core_palette
from app.services.storage import get_storage

router = APIRouter(prefix="/api", tags=["projects"])


def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    proj = db.get(Project, project_id)
    if proj is None or proj.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在")
    return proj


def _briefs(db: Session, project_id: uuid.UUID) -> list[dict]:
    rows = db.scalars(select(Pattern).where(Pattern.project_id == project_id)
                      .order_by(Pattern.created_at.desc())).all()
    # ai_render_id 要带上：版本列表靠它区分"这版是 AI 出的还是原图出的"，
    # origin 说的是另一件事（怎么产生的：generated / edited / patched）。
    return [{"id": p.id, "origin": p.origin, "parent_id": p.parent_id,
             "ai_render_id": p.ai_render_id,
             "created_at": p.created_at, "score": (p.buildability or {}).get("score"),
             "n_colors": len(p.color_stats or {}),
             # 尺寸：首页卡片上要写"58×44 格"，不能只写"58 格"
             "rows": len(p.grid or []), "cols": len((p.grid or [[]])[0])} for p in rows]


def _project_out(db: Session, proj: Project) -> dict:
    return {"id": proj.id, "name": proj.name, "created_at": proj.created_at,
            "patterns": _briefs(db, proj.id)}


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(name: str = Form("未命名"), file: UploadFile = File(...),
                   user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    proj = psvc.create_project(db, user.id, name, file.file.read())
    db.commit()
    return _project_out(db, proj)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Project).where(Project.user_id == user.id)
                      .order_by(Project.created_at.desc())).all()
    return [_project_out(db, p) for p in rows]


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> dict:
    return _project_out(db, _owned_project(db, user, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def rename_project(project_id: uuid.UUID, body: ProjectRenameIn,
                   user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """上传时不再问名字（出结果前不该问任何问题），名字默认取文件名，事后在这里改。"""
    proj = _owned_project(db, user, project_id)
    proj.name = body.name
    db.commit()
    return _project_out(db, proj)


@router.get("/projects/{project_id}/source")
def get_source(project_id: uuid.UUID, user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> Response:
    proj = _owned_project(db, user, project_id)
    return Response(get_storage().load(proj.source_image_path), media_type="image/png")


@router.get("/projects/{project_id}/ai-renders/{render_id}/image")
def get_ai_render(project_id: uuid.UUID, render_id: uuid.UUID,
                  user: User = Depends(current_user),
                  db: Session = Depends(get_db)) -> Response:
    """AI 重绘的成品图。前端拿它和原图做对比切换。

    归属检查走 project——AiRender 本身没有 user_id，只能经由 project 认人。
    """
    _owned_project(db, user, project_id)
    render = db.get(AiRender, render_id)
    if render is None or render.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AI 图不存在")
    if render.output_path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"AI 图尚未生成（状态 {render.status}）")
    return Response(get_storage().load(render.output_path), media_type="image/png")


@router.get("/projects/{project_id}/suggest-sizes", response_model=list[SizeSuggestion])
def suggest_sizes(project_id: uuid.UUID, base: int = 58, user: User = Depends(current_user),
                  db: Session = Depends(get_db)) -> list[dict]:
    if not (8 <= base <= 200):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "base 必须在 8..200 之间")
    proj = _owned_project(db, user, project_id)
    return pipeline.suggest_sizes(get_storage().load(proj.source_image_path), base)


@router.post("/projects/{project_id}/generate", response_model=JobOut,
             status_code=status.HTTP_202_ACCEPTED)
def generate(project_id: uuid.UUID, body: GenerateIn, background: BackgroundTasks,
             user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    proj = _owned_project(db, user, project_id)
    psvc.params_from_dict(body.params)          # 提前校验，坏参数不入队

    if body.use_ai:
        if body.style_preset_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "use_ai=true 时必须指定 style_preset_id")
        if db.get(StylePreset, body.style_preset_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "风格预设不存在")
        if quota.remaining(db, user.id) < 1:
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                                "AI 额度不足，可跳过 AI 直接出图")

    job = jsvc.enqueue(db, jsvc.JOB_GENERATE, {
        "project_id": str(proj.id), "user_id": str(user.id), "use_ai": body.use_ai,
        "style_preset_id": str(body.style_preset_id) if body.style_preset_id else None,
        "provider": body.provider, "params": body.params,
    })
    db.commit()
    background.add_task(jsvc.run_generate_job, SessionLocal, job.id)
    return {"id": job.id, "type": job.type, "status": job.status,
            "result": job.result, "error": job.error, "created_at": job.created_at}


@router.post("/projects/{project_id}/patterns")
def recompute(project_id: uuid.UUID, body: PatternParamsIn,
              user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """同步重算——调参是百毫秒级操作，走队列反而拖慢体验。"""
    from app.api.patterns import pattern_out

    proj = _owned_project(db, user, project_id)
    params = psvc.params_from_dict(body.params)
    ai_render = None
    if body.source != "original" and body.ai_render_id is not None:
        ai_render = db.get(AiRender, body.ai_render_id)
        if ai_render is None or ai_render.project_id != proj.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "AI 重绘结果不存在")
    pat = psvc.generate(db, proj, params, ai_render)
    db.flush()                      # 先拿到新版本的 id，再决定删不删旧的
    replaced = (psvc.discard_draft(db, proj, body.replaces, keep=pat.id)
                if body.replaces is not None else None)
    db.commit()                     # 新增和删除在同一个事务里：出图失败就什么都不删
    out = pattern_out(pat, load_core_palette(params.palette_id))
    out["replaced_id"] = replaced   # 让前端知道要不要从版本列表里拿掉那一行
    return out
