from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import SessionLocal
from app.providers.base import ProviderError
from app.services.auth import AuthError
from app.services.jobs import reclaim_stale
from app.services.palettes import seed_palettes
from app.services.patterns import PatternError
from app.services.quota import QuotaExceeded

log = logging.getLogger("pindou")


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthError)
    def _auth(_: Request, exc: AuthError) -> JSONResponse:
        code = (status.HTTP_401_UNAUTHORIZED if "用户名或密码错误" in exc.message
                else status.HTTP_400_BAD_REQUEST)
        return JSONResponse({"detail": exc.message}, status_code=code)

    @app.exception_handler(QuotaExceeded)
    def _quota(_: Request, exc: QuotaExceeded) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_402_PAYMENT_REQUIRED)

    @app.exception_handler(PatternError)
    def _pattern(_: Request, exc: PatternError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=status.HTTP_400_BAD_REQUEST)

    @app.exception_handler(ProviderError)
    def _provider(_: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse({"detail": f"AI 服务不可用：{exc.message}。可跳过 AI 直接出图。"},
                            status_code=status.HTTP_502_BAD_GATEWAY)


def _startup() -> None:
    db = SessionLocal()
    try:
        n = reclaim_stale(db)
        seeded = seed_palettes(db)
        db.commit()
        if n:
            log.warning("启动清理：%d 个中断的任务已标记失败并退还额度", n)
        if seeded:
            log.info("色卡 seed：写入 %d 个色号", seeded)
    finally:
        db.close()


def create_app(run_startup: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if run_startup:
            _startup()
        yield

    app = FastAPI(title="馨豆 · 拼豆图纸", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
    _install_error_handlers(app)

    from app.api import admin as admin_api
    from app.api import auth as auth_api
    from app.api import jobs as jobs_api
    from app.api import meta as meta_api
    from app.api import patterns as patterns_api
    from app.api import projects as projects_api

    for module in (auth_api, projects_api, patterns_api, jobs_api, meta_api, admin_api):
        app.include_router(module.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
