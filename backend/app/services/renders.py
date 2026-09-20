from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AiRender, Project, StylePreset
from app.providers.base import ProviderError, call_with_retry, get_provider
from app.services import quota
from app.services.storage import get_storage


def input_hash(image_bytes: bytes, prompt: str, params: dict) -> str:
    h = hashlib.sha256()
    h.update(hashlib.sha256(image_bytes).digest())
    h.update(prompt.encode("utf-8"))
    h.update(json.dumps(params or {}, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()


def _provider_for(name: str | None):
    return get_provider(name)


def find_cached(db: Session, project_id: uuid.UUID, ihash: str,
                style_preset_id: uuid.UUID | None) -> AiRender | None:
    row = db.scalar(select(AiRender).where(
        AiRender.project_id == project_id,
        AiRender.input_hash == ihash,
        AiRender.style_preset_id == style_preset_id,
        AiRender.status == "done"))
    if row is None or not row.output_path:
        return None
    return row if get_storage().exists(row.output_path) else None


def redraw(db: Session, user_id: uuid.UUID, project: Project, style_preset: StylePreset,
           provider_name: str | None = None) -> AiRender:
    """命中缓存不扣额度；否则先扣后跑，失败退回。"""
    st = get_storage()
    image_bytes = st.load(project.source_image_path)
    params = dict(style_preset.params or {})
    ihash = input_hash(image_bytes, style_preset.prompt, params)

    cached = find_cached(db, project.id, ihash, style_preset.id)
    if cached is not None:
        return cached

    provider = _provider_for(provider_name)
    quota.reserve(db, user_id)

    record = AiRender(project_id=project.id, provider=provider.name,
                      model=getattr(getattr(provider, "cfg", None), "model", provider.name),
                      style_preset_id=style_preset.id, prompt=style_preset.prompt,
                      params=params, input_hash=ihash, status="running")
    db.add(record)
    db.flush()

    try:
        result = call_with_retry(provider, image_bytes, style_preset.prompt, params)
    except ProviderError as e:
        record.status = "failed"
        record.error = e.message[:2000]
        quota.refund(db, user_id)
        db.flush()
        raise

    key = hashlib.sha256(result.image).hexdigest()
    record.output_path = st.save("ai_renders", key, result.image, ".png")
    record.model = result.model
    record.cost = result.cost
    record.status = "done"
    db.flush()
    return record
