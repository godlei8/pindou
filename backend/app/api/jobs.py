from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import Job, User
from app.schemas import JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, user: User = Depends(current_user),
            db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None or (job.payload or {}).get("user_id") != str(user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return job
