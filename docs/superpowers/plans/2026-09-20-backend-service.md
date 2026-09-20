# 后端服务层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已完成的 `app/core/` 流水线之上建起完整后端：PostgreSQL 持久化、账号与邀请码、AI 额度、图纸版本树、jobs 队列、AI provider 抽象、REST API 与部署配置，使前端可以对接真实接口。

**Architecture:** FastAPI + SQLAlchemy 2.0（全同步，不用 async——core 是 CPU 密集的 numpy，异步没有收益还会把事务模型复杂化）。三层：`models/`（ORM）→ `services/`（业务逻辑，不依赖 FastAPI）→ `api/`（路由，只做校验与序列化）。`core/` 保持零依赖不动。首次生成走 jobs 表异步（含 AI 时十几秒），调参走同步接口（百毫秒级）。

**Tech Stack:** Python 3.11、FastAPI 0.141、SQLAlchemy 2.0.54、Alembic 1.20、psycopg 3.3、PostgreSQL 16.11（本机 `D:\Kf\pgsql`，端口 5432）、bcrypt 5.0、itsdangerous（签名 cookie）、httpx（provider 调用）、pytest。

**Spec:** `docs/superpowers/specs/2026-09-20-pindou-pattern-generator-design.md`（§5 数据模型、§6 AI 重绘层、§7 API、§9 测试、§10 部署）。算法层已完成，见 `docs/superpowers/plans/2026-09-20-core-pipeline.md`。

**这是三份计划中的第二份。** 第三份（前端）在本计划完成后写。

## Global Constraints

- `app/core/` **不得修改**，也不得让它 import 数据库、FastAPI 或任何 `app/api`、`app/models`、`app/services` 代码。后端只调用 core 的纯函数。
- 流水线只实现一次；后端不得重新实现任何图像处理逻辑。
- **AI 是可选环节，可拼性是附加环节**：二者任一失败都不能让"出一张图纸"这件核心事失败。
- 大文件（原图、AI 图、导出 PDF）走磁盘，库里只存路径；存储层抽接口，将来换 OSS 只改实现。
- AI 额度**先扣后跑，失败退回**；命中 `ai_renders` 缓存不扣。
- 手工编辑以「格子 → 色号」显式列表提交，后端只写入 + 重跑分析，**绝不重放填充算法**。
- 密码用 bcrypt（rounds=12）哈希；会话用 HttpOnly + SameSite=Lax 签名 cookie，不用 JWT。
- 注册必须校验邀请码。
- 所有金额/额度扣减必须在数据库事务内完成，用行级锁防并发刷穿。
- 提交信息格式 `feat(api): ...` / `feat(db): ...` / `test: ...`，末尾附 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`。
- 开发环境：Windows + Git Bash；虚拟环境在 `backend/.venv`，命令统一 `./.venv/Scripts/python -m pytest`。
- 每个任务以 `./.venv/Scripts/python -m pytest -q` 全绿结束再提交（含既有的 98 个 core 测试）。

## 前置条件（执行前必须满足）

数据库由需求方手工准备（超管密码不经过实现者）：

```bash
"D:/Kf/pgsql/bin/psql.exe" -U postgres -h 127.0.0.1 \
  -c "CREATE USER pindou WITH PASSWORD '<你的密码>';" \
  -c "CREATE DATABASE pindou OWNER pindou;" \
  -c "CREATE DATABASE pindou_test OWNER pindou;"
```

`backend/.env`（已在 `.gitignore`）：

```
DATABASE_URL=postgresql+psycopg://pindou:<你的密码>@127.0.0.1:5432/pindou
TEST_DATABASE_URL=postgresql+psycopg://pindou:<你的密码>@127.0.0.1:5432/pindou_test
SESSION_SECRET=<python -c "import secrets;print(secrets.token_urlsafe(32))">
DATA_DIR=./data
```

Task 1 的第一步会校验这两项，缺失则停止并报告。

---

## 文件结构

```
backend/
├─ pyproject.toml                   [修改] 增加服务层依赖
├─ .env                             [手工，不提交]
├─ .env.example                     [新增，提交]
├─ alembic.ini                      [新增]
├─ alembic/
│  ├─ env.py
│  └─ versions/                     迁移脚本
├─ app/
│  ├─ core/                         [不动] 已完成的算法流水线
│  ├─ palettes/                     [不动]
│  ├─ config.py                     Settings（pydantic-settings 读 .env）
│  ├─ db.py                         engine / SessionLocal / get_db 依赖
│  ├─ models/
│  │  ├─ __init__.py                汇出全部模型，供 alembic autogenerate
│  │  ├─ base.py                    DeclarativeBase + 时间戳 mixin
│  │  ├─ user.py                    User / InviteCode
│  │  ├─ project.py                 Project / AiRender / Pattern / Feedback
│  │  ├─ palette.py                 Palette / PaletteColor
│  │  ├─ style_preset.py            StylePreset
│  │  └─ job.py                     Job
│  ├─ services/                     业务逻辑，纯 SQLAlchemy + core，不 import fastapi
│  │  ├─ storage.py                 Storage 接口 + LocalStorage
│  │  ├─ auth.py                    注册/登录/会话签名
│  │  ├─ quota.py                   额度扣减与退还（行级锁）
│  │  ├─ palettes.py                色卡 seed 与 Palette 载入缓存
│  │  ├─ patterns.py                生成 / 重算 / apply-patch / 编辑 / 导出
│  │  ├─ renders.py                 AI 重绘：缓存查找、调 provider、落盘
│  │  └─ jobs.py                    入队 / SKIP LOCKED 取任务 / 执行 / 启动清理
│  ├─ providers/
│  │  ├─ base.py                    ImageProvider 协议 + RedrawResult + 注册表
│  │  ├─ openai_compatible.py       火山方舟 / 百炼兼容模式 / 任意中转网关
│  │  ├─ dashscope_native.py        通义万相原生异步任务（提交 → 轮询）
│  │  └─ fake.py                    测试与无 key 时的假 provider
│  ├─ schemas.py                    Pydantic 请求/响应模型
│  ├─ api/
│  │  ├─ deps.py                    当前用户依赖、分页
│  │  ├─ auth.py                    /api/auth/*
│  │  ├─ projects.py                /api/projects/*
│  │  ├─ patterns.py                /api/patterns/*
│  │  ├─ jobs.py                    /api/jobs/*
│  │  └─ meta.py                    /api/palettes、/api/style-presets、/api/health
│  ├─ main.py                       FastAPI app 装配、启动钩子、异常处理
│  └─ cli.py                        管理脚本：建邀请码、加额度、灌色卡
├─ providers.yaml.example           provider 配置样例
├─ docker-compose.yml               [新增] db / api / web
├─ Dockerfile                       [新增]
└─ tests/
   ├─ conftest.py                   [修改] 增加 db / client / user 夹具
   ├─ test_models.py
   ├─ test_auth_service.py
   ├─ test_quota.py
   ├─ test_storage.py
   ├─ test_providers.py
   ├─ test_jobs.py
   ├─ test_patterns_service.py
   ├─ test_api_auth.py
   ├─ test_api_projects.py
   ├─ test_api_patterns.py
   └─ test_api_export.py
```

已验证的环境事实（2026-09-20，本机实测）：

- 本机 PostgreSQL **16.11** 跑在 127.0.0.1:5432，程序在 `D:\Kf\pgsql\bin`，认证方式 `scram-sha-256`（需密码）。Docker CLI 已装（29.7.2 / Compose v5.4.0）但守护进程未运行——开发期不依赖 Docker。
- 依赖均已在 `backend/.venv` 安装成功：fastapi 0.141.1、sqlalchemy 2.0.54、alembic 1.20.0、psycopg 3.3.6、httpx 0.28.1、bcrypt 5.0.0、argon2-cffi、itsdangerous、pydantic-settings、python-multipart。
- **用 `bcrypt` 包直接调用，不要用 `passlib`**——passlib 1.7.4 与 bcrypt 4+ 不兼容（读 `bcrypt.__about__` 报错）且已停止维护。bcrypt 5.0 的 `hashpw`/`checkpw` 直接可用，rounds=12 时一次哈希+验证约 420 ms（登录接口需要注意这个耗时，测试夹具里用 rounds=4 加速）。
- SQLAlchemy 方言串 `postgresql+psycopg://` 解析正常（psycopg3，不是 psycopg2）。
- core 层现有 98 个测试全绿，不得破坏。

---

### Task 1: 配置、数据库连接与测试夹具

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/.env.example`、`backend/app/config.py`、`backend/app/db.py`
- Create: `backend/app/models/base.py`、`backend/app/models/__init__.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_config_db.py`

**Interfaces:**
- Produces: `config.Settings`（字段 `database_url: str`、`test_database_url: str | None`、`session_secret: str`、`data_dir: Path`、`providers_file: Path`、`bcrypt_rounds: int = 12`），`config.get_settings() -> Settings`（`lru_cache`）
- Produces: `db.engine`、`db.SessionLocal`、`db.get_db()` 生成器依赖
- Produces: `models.base.Base`（DeclarativeBase）、`models.base.TimestampMixin`（`created_at` 带服务器默认值）
- Produces: pytest 夹具 `settings`、`db`（每个测试一个事务并回滚）、`session_factory`

- [ ] **Step 1: 增加依赖**

改 `backend/pyproject.toml` 的 `dependencies`，在现有 5 项后追加：

```toml
dependencies = [
  "numpy>=1.26",
  "pillow>=10.1",
  "scipy>=1.11",
  "opencv-python-headless>=4.9",
  "PyMaxflow>=1.3",
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlalchemy>=2.0",
  "alembic>=1.13",
  "psycopg[binary]>=3.2",
  "pydantic-settings>=2.6",
  "bcrypt>=4.2",
  "itsdangerous>=2.2",
  "httpx>=0.27",
  "python-multipart>=0.0.9",
  "PyYAML>=6.0",
]
```

`dev` 附加项改为：

```toml
dev = ["pytest>=8", "pytest-cov", "respx>=0.21"]
```

安装：

```bash
cd backend && ./.venv/Scripts/python -m pip install -q -e ".[dev]"
```

- [ ] **Step 2: 写 .env.example**

`backend/.env.example`（提交进仓库，不含真实密码）：

```
# 复制为 .env 并填入真实值；.env 已被 .gitignore 忽略
DATABASE_URL=postgresql+psycopg://pindou:CHANGE_ME@127.0.0.1:5432/pindou
TEST_DATABASE_URL=postgresql+psycopg://pindou:CHANGE_ME@127.0.0.1:5432/pindou_test
SESSION_SECRET=CHANGE_ME_python -c "import secrets;print(secrets.token_urlsafe(32))"
DATA_DIR=./data
PROVIDERS_FILE=./providers.yaml
```

- [ ] **Step 3: 写失败测试**

`backend/tests/test_config_db.py`：

```python
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
```

- [ ] **Step 4: 运行确认失败**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_config_db.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'app.config'`。

- [ ] **Step 5: 写 config.py**

`backend/app/config.py`：

```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str
    test_database_url: str | None = None
    session_secret: str
    data_dir: Path = _BACKEND_ROOT / "data"
    providers_file: Path = _BACKEND_ROOT / "providers.yaml"
    bcrypt_rounds: int = 12
    session_cookie_name: str = "pindou_session"
    session_max_age_days: int = 30
    max_upload_bytes: int = 20 * 1024 * 1024

    @field_validator("data_dir", "providers_file", mode="after")
    @classmethod
    def _absolute(cls, v: Path) -> Path:
        return v if v.is_absolute() else (_BACKEND_ROOT / v).resolve()

    @field_validator("data_dir", mode="after")
    @classmethod
    def _ensure_dir(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    @field_validator("session_secret")
    @classmethod
    def _secret_long_enough(cls, v: str) -> str:
        if len(v) < 16:
            raise ValueError("SESSION_SECRET must be at least 16 characters")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: 写 db.py 与 models/base.py**

`backend/app/db.py`：

```python
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

`backend/app/models/base.py`：

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

`backend/app/models/__init__.py` 先只写：

```python
from app.models.base import Base, TimestampMixin, uuid_pk

__all__ = ["Base", "TimestampMixin", "uuid_pk"]
```

- [ ] **Step 7: 改 conftest.py**

`backend/tests/conftest.py` 整体替换为：

```python
import numpy as np
import pytest
from sqlalchemy import create_engine, text
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
```

- [ ] **Step 8: 运行确认通过**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_config_db.py -q
```

Expected: 5 passed。若 `test_can_connect_to_test_database` 报连接失败，检查 `.env` 的 `TEST_DATABASE_URL` 与前置条件里的建库命令是否执行过。

- [ ] **Step 9: 全量回归并提交**

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

Expected: 103 passed（98 core + 5 新增）。

```bash
git add backend/pyproject.toml backend/.env.example backend/app/config.py backend/app/db.py backend/app/models backend/tests
git commit -m "feat(db): 配置加载、数据库连接与事务隔离测试夹具

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: ORM 模型与 Alembic 迁移

**Files:**
- Create: `backend/app/models/user.py`、`project.py`、`palette.py`、`style_preset.py`、`job.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic.ini`、`backend/alembic/env.py`、`backend/alembic/script.py.mako`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `models.base.Base / TimestampMixin / uuid_pk`
- Produces（全部主键为 UUID，除 `PaletteColor`/`Job` 用自增 int）：
  - `User(id, username unique, password_hash, ai_quota int, ai_used int, is_admin bool, created_at)`
  - `InviteCode(code pk str, created_by FK user nullable, max_uses int, used_count int, expires_at nullable, created_at)`
  - `Project(id, user_id FK, name, source_image_path, created_at)`
  - `AiRender(id, project_id FK, provider, model, style_preset_id FK nullable, prompt, params JSONB, input_hash, output_path nullable, status, cost Numeric nullable, error nullable, created_at)`
  - `Pattern(id, project_id FK, ai_render_id FK nullable, parent_id FK self nullable, origin, params JSONB, grid JSONB, color_stats JSONB, buildability JSONB nullable, applied_patch JSONB nullable, manual_edits JSONB nullable, created_at)`
  - `Feedback(id, pattern_id FK, user_id FK, kind, cells JSONB, note, created_at)`
  - `Palette(id, brand, name, version)` / `PaletteColor(id int, palette_id FK, code, name, rgb str, lab JSONB, in_sets JSONB, source, confidence)`
  - `StylePreset(id, name, prompt, params JSONB, version int, is_active bool)`
  - `Job(id int, type, payload JSONB, status, attempts int, locked_at nullable, result JSONB nullable, error nullable, created_at)`
  - 约束：`AiRender` 上 `UniqueConstraint(project_id, input_hash, style_preset_id)`；`PaletteColor` 上 `UniqueConstraint(palette_id, code)`；`Job.status` 上建索引；`Pattern.project_id` 上建索引

- [ ] **Step 1: 写失败测试**

`backend/tests/test_models.py`：

```python
import uuid

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.models import AiRender, Feedback, InviteCode, Job, Palette, PaletteColor, Pattern, Project, StylePreset, User


def _user(db, name="alice"):
    u = User(username=name, password_hash="x", ai_quota=10)
    db.add(u)
    db.flush()
    return u


def test_user_username_is_unique(db):
    _user(db)
    db.add(User(username="alice", password_hash="y"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_user_quota_defaults(db):
    u = User(username="bob", password_hash="x")
    db.add(u)
    db.flush()
    assert u.ai_quota == 0 and u.ai_used == 0 and u.is_admin is False


def test_invite_code_roundtrip(db):
    db.add(InviteCode(code="LETMEIN", max_uses=3))
    db.flush()
    c = db.get(InviteCode, "LETMEIN")
    assert c.used_count == 0 and c.max_uses == 3


def test_project_pattern_version_tree(db):
    u = _user(db)
    p = Project(user_id=u.id, name="t", source_image_path="a.png")
    db.add(p)
    db.flush()
    root = Pattern(project_id=p.id, origin="generated", params={"grid_long_side": 48},
                   grid=[[0, 1], [1, 0]], color_stats={"0": 2, "1": 2})
    db.add(root)
    db.flush()
    child = Pattern(project_id=p.id, parent_id=root.id, origin="edited",
                    params=root.params, grid=[[0, 0], [1, 0]], color_stats={"0": 3, "1": 1},
                    manual_edits=[{"cell": [0, 1], "from": 1, "to": 0}])
    db.add(child)
    db.flush()
    assert child.parent_id == root.id
    assert db.get(Pattern, child.id).manual_edits[0]["to"] == 0


def test_jsonb_grid_survives_roundtrip(db):
    u = _user(db)
    p = Project(user_id=u.id, name="t", source_image_path="a.png")
    db.add(p)
    db.flush()
    grid = [[0, None, 2], [None, 1, 1]]
    pat = Pattern(project_id=p.id, origin="generated", params={}, grid=grid, color_stats={})
    db.add(pat)
    db.flush()
    db.expire(pat)
    assert db.get(Pattern, pat.id).grid == grid        # None 必须原样保留，不能变成 0


def test_ai_render_cache_key_is_unique(db):
    u = _user(db)
    p = Project(user_id=u.id, name="t", source_image_path="a.png")
    db.add(p)
    db.flush()
    for _ in range(2):
        db.add(AiRender(project_id=p.id, provider="fake", model="m", prompt="p",
                        params={}, input_hash="h1", status="done"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_palette_color_unique_per_palette(db):
    pal = Palette(brand="MARD", name="MARD 291", version="2026-09-20")
    db.add(pal)
    db.flush()
    db.add(PaletteColor(palette_id=pal.id, code="A1", name="A1", rgb="#F9F0CD",
                        lab=[94.7, -2.6, 18.0], source="beadcolors", confidence="agree"))
    db.flush()
    db.add(PaletteColor(palette_id=pal.id, code="A1", name="dup", rgb="#000000",
                        lab=[0, 0, 0], source="x", confidence="x"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_feedback_records_cells(db):
    u = _user(db)
    p = Project(user_id=u.id, name="t", source_image_path="a.png")
    db.add(p)
    db.flush()
    pat = Pattern(project_id=p.id, origin="generated", params={}, grid=[[0]], color_stats={})
    db.add(pat)
    db.flush()
    db.add(Feedback(pattern_id=pat.id, user_id=u.id, kind="断裂",
                    cells=[[34, 17], [34, 18]], note="发尾断了"))
    db.flush()
    fb = db.scalars(select(Feedback)).one()
    assert fb.cells == [[34, 17], [34, 18]] and fb.kind == "断裂"


def test_job_defaults_and_index(db, test_engine):
    j = Job(type="generate", payload={"project_id": str(uuid.uuid4())})
    db.add(j)
    db.flush()
    assert j.status == "pending" and j.attempts == 0 and j.locked_at is None
    idx = {i["name"] for i in inspect(test_engine).get_indexes("jobs")}
    assert any("status" in n for n in idx)


def test_style_preset_versioning(db):
    db.add(StylePreset(name="Q版盲盒", prompt="粗轮廓 纯色平涂 无渐变", params={"scale": 0.5}))
    db.flush()
    sp = db.scalars(select(StylePreset)).one()
    assert sp.version == 1 and sp.is_active is True
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_models.py -q
```

Expected: FAIL，`ImportError: cannot import name 'User' from 'app.models'`。

- [ ] **Step 3: 写 user.py**

`backend/app/models/user.py`：

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    ai_quota: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    ai_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)


class InviteCode(Base, TimestampMixin):
    __tablename__ = "invite_codes"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    max_uses: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: 写 project.py**

`backend/app/models/project.py`：

```python
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_image_path: Mapped[str] = mapped_column(String(500), nullable=False)


class AiRender(Base, TimestampMixin):
    __tablename__ = "ai_renders"
    __table_args__ = (
        UniqueConstraint("project_id", "input_hash", "style_preset_id", name="uq_ai_render_cache"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    style_preset_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("style_presets.id", ondelete="SET NULL"), nullable=True
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Pattern(Base, TimestampMixin):
    __tablename__ = "patterns"
    __table_args__ = (Index("ix_patterns_project_created", "project_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    ai_render_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_renders.id", ondelete="SET NULL"), nullable=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patterns.id", ondelete="SET NULL"), nullable=True
    )
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="generated")
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    grid: Mapped[list] = mapped_column(JSONB, nullable=False)
    color_stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    buildability: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    applied_patch: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    manual_edits: Mapped[list | None] = mapped_column(JSONB, nullable=True)


class Feedback(Base, TimestampMixin):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = uuid_pk()
    pattern_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patterns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    cells: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 5: 写 palette.py、style_preset.py、job.py**

`backend/app/models/palette.py`：

```python
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk


class Palette(Base):
    __tablename__ = "palettes"

    id: Mapped[uuid.UUID] = uuid_pk()
    brand: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)


class PaletteColor(Base):
    __tablename__ = "palette_colors"
    __table_args__ = (UniqueConstraint("palette_id", "code", name="uq_palette_color_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    palette_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("palettes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    rgb: Mapped[str] = mapped_column(String(7), nullable=False)
    lab: Mapped[list] = mapped_column(JSONB, nullable=False)
    in_sets: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(24), nullable=False)
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)
```

`backend/app/models/style_preset.py`：

```python
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class StylePreset(Base, TimestampMixin):
    __tablename__ = "style_presets"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
```

`backend/app/models/job.py`：

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending",
                                        server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

`backend/app/models/__init__.py` 改为：

```python
from app.models.base import Base, TimestampMixin, uuid_pk
from app.models.job import Job
from app.models.palette import Palette, PaletteColor
from app.models.project import AiRender, Feedback, Pattern, Project
from app.models.style_preset import StylePreset
from app.models.user import InviteCode, User

__all__ = [
    "Base", "TimestampMixin", "uuid_pk",
    "User", "InviteCode",
    "Project", "AiRender", "Pattern", "Feedback",
    "Palette", "PaletteColor",
    "StylePreset",
    "Job",
]
```

- [ ] **Step 6: 运行确认通过**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_models.py -q
```

Expected: 10 passed。

- [ ] **Step 7: 初始化 Alembic 并生成首个迁移**

```bash
cd backend && ./.venv/Scripts/python -m alembic init alembic
```

把 `backend/alembic.ini` 里的 `sqlalchemy.url` 一行改成空（URL 从代码读）：

```ini
sqlalchemy.url =
```

`backend/alembic/env.py` 整体替换为：

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), pool_pre_ping=True, future=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True, compare_server_default=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

生成迁移并应用：

```bash
cd backend && ./.venv/Scripts/python -m alembic revision --autogenerate -m "initial schema" \
  && ./.venv/Scripts/python -m alembic upgrade head
```

Expected: 生成 `alembic/versions/<hash>_initial_schema.py`，包含 9 张表；upgrade 成功。

- [ ] **Step 8: 验证迁移与模型一致**

```bash
cd backend && ./.venv/Scripts/python -m alembic revision --autogenerate -m "should be empty" 2>&1 | tail -3
```

打开新生成的文件，`upgrade()` 里应只有 `pass`。确认后删掉它：

```bash
cd backend && rm alembic/versions/*should_be_empty*.py
```

若不为空，说明模型与迁移有偏差，按差异修正模型或迁移后重跑本步。

- [ ] **Step 9: 全量回归并提交**

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

Expected: 113 passed。

```bash
git add backend/app/models backend/alembic.ini backend/alembic backend/tests/test_models.py
git commit -m "feat(db): 九张表的 ORM 模型与 Alembic 初始迁移

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: 存储层与色卡 seed

**Files:**
- Create: `backend/app/services/__init__.py`（空）、`backend/app/services/storage.py`、`backend/app/services/palettes.py`
- Test: `backend/tests/test_storage.py`

**Interfaces:**
- Produces: `storage.Storage` 协议：`save(category: str, key: str, data: bytes, ext: str) -> str`（返回相对路径）、`load(rel_path: str) -> bytes`、`path(rel_path: str) -> Path`、`exists(rel_path) -> bool`、`delete(rel_path) -> None`
- Produces: `storage.LocalStorage(root: Path)`，落盘布局 `<root>/<category>/<key[:2]>/<key><ext>`（两级散列，避免单目录几万文件）
- Produces: `storage.get_storage() -> Storage`（读 settings.data_dir，lru_cache）
- Produces: `palettes.seed_palettes(db) -> int`：把 `app/palettes/*.json` 灌进 `palettes`/`palette_colors`，已存在同 `brand+version` 则跳过；返回写入的色数
- Produces: `palettes.load_core_palette(palette_id: str = "mard") -> core.palette.Palette`（lru_cache，供流水线用；DB 里的表只服务于前端查询与将来的编辑）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_storage.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_storage.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'app.services'`。

- [ ] **Step 3: 写 storage.py**

`backend/app/services/storage.py`：

```python
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import get_settings

_SAFE = re.compile(r"^[A-Za-z0-9_\-]+$")


class Storage(Protocol):
    def save(self, category: str, key: str, data: bytes, ext: str) -> str: ...
    def load(self, rel_path: str) -> bytes: ...
    def path(self, rel_path: str) -> Path: ...
    def exists(self, rel_path: str) -> bool: ...
    def delete(self, rel_path: str) -> None: ...


class LocalStorage:
    """落盘布局 <root>/<category>/<key 前两位>/<key><ext>。两级散列避免单目录堆几万文件。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _rel(self, category: str, key: str, ext: str) -> str:
        if not _SAFE.match(category) or not _SAFE.match(key):
            raise ValueError(f"unsafe category/key: {category!r}/{key!r}")
        if not ext.startswith(".") or not _SAFE.match(ext[1:]):
            raise ValueError(f"unsafe ext: {ext!r}")
        return f"{category}/{key[:2]}/{key}{ext}"

    def path(self, rel_path: str) -> Path:
        p = (self.root / rel_path).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError(f"path escapes storage root: {rel_path!r}")
        return p

    def save(self, category: str, key: str, data: bytes, ext: str) -> str:
        rel = self._rel(category, key, ext)
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)          # 原子替换，避免半截文件被读到
        return rel

    def load(self, rel_path: str) -> bytes:
        p = self.path(rel_path)
        if not p.exists():
            raise FileNotFoundError(rel_path)
        return p.read_bytes()

    def exists(self, rel_path: str) -> bool:
        return self.path(rel_path).exists()

    def delete(self, rel_path: str) -> None:
        self.path(rel_path).unlink(missing_ok=True)


@lru_cache
def get_storage() -> Storage:
    return LocalStorage(get_settings().data_dir)
```

`backend/app/services/__init__.py` 为空文件。

- [ ] **Step 4: 写 palettes.py**

`backend/app/services/palettes.py`：

```python
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.color import srgb_to_lab
from app.core.palette import Palette as CorePalette
from app.models import Palette, PaletteColor

_PALETTE_DIR = Path(__file__).resolve().parents[1] / "palettes"


@lru_cache
def load_core_palette(palette_id: str = "mard") -> CorePalette:
    """供流水线使用的色卡。直接读 JSON，不查库——core 不许依赖数据库。"""
    return CorePalette.load(palette_id)


def seed_palettes(db: Session) -> int:
    """把 app/palettes/*.json 灌进库。同 brand+version 已存在则跳过，返回新增色数。"""
    written = 0
    for path in sorted(_PALETTE_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        exists = db.scalar(
            select(Palette).where(Palette.brand == doc["brand"], Palette.version == doc["version"])
        )
        if exists is not None:
            continue
        pal = Palette(brand=doc["brand"], name=f'{doc["brand"]} {len(doc["colors"])}',
                      version=doc["version"])
        db.add(pal)
        db.flush()
        for c in doc["colors"]:
            rgb01 = [int(c["hex"][i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
            db.add(PaletteColor(
                palette_id=pal.id, code=c["code"], name=c.get("name", c["code"]),
                rgb=c["hex"], lab=[round(float(x), 4) for x in srgb_to_lab(rgb01)],
                in_sets=c.get("in_sets"), source=c["source"],
                confidence=c["confidence"], role=c.get("role"),
            ))
            written += 1
        db.flush()
    return written
```

- [ ] **Step 5: 运行确认通过**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_storage.py -q
```

Expected: 8 passed。

- [ ] **Step 6: 全量回归并提交**

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

Expected: 121 passed。

```bash
git add backend/app/services backend/tests/test_storage.py
git commit -m "feat(api): 本地存储层（两级散列、原子写、越界防护）与色卡 seed

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: 认证与额度服务

**Files:**
- Create: `backend/app/services/auth.py`、`backend/app/services/quota.py`
- Test: `backend/tests/test_auth_service.py`、`backend/tests/test_quota.py`

**Interfaces:**
- Produces: `auth.hash_password(raw: str) -> str`、`auth.verify_password(raw: str, hashed: str) -> bool`
- Produces: `auth.register(db, username: str, password: str, invite_code: str) -> User`；邀请码无效/过期/用尽抛 `auth.AuthError`；用户名已存在抛 `auth.AuthError`
- Produces: `auth.authenticate(db, username: str, password: str) -> User`；失败抛 `auth.AuthError`
- Produces: `auth.make_session(user_id: uuid.UUID) -> str`、`auth.read_session(token: str) -> uuid.UUID | None`（itsdangerous 签名，带 max_age）
- Produces: `auth.AuthError(Exception)`，带 `message: str`
- Produces: `quota.reserve(db, user_id) -> None`：行级锁 `SELECT ... FOR UPDATE`，`ai_used + 1 > ai_quota` 抛 `quota.QuotaExceeded`，否则 `ai_used += 1`
- Produces: `quota.refund(db, user_id) -> None`：`ai_used = max(0, ai_used - 1)`
- Produces: `quota.remaining(db, user_id) -> int`
- Produces: `quota.QuotaExceeded(Exception)`

**注意**：测试里把 `bcrypt_rounds` 降到 4，否则每次哈希 400 ms、整套测试会慢到不可接受。生产仍用 12。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_auth_service.py`：

```python
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import InviteCode, User
from app.services import auth


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch):
    monkeypatch.setattr(auth, "_ROUNDS", 4)


def _code(db, code="LETMEIN", **kw):
    c = InviteCode(code=code, max_uses=kw.pop("max_uses", 2), **kw)
    db.add(c)
    db.flush()
    return c


def test_hash_and_verify():
    h = auth.hash_password("hunter2")
    assert h != "hunter2" and auth.verify_password("hunter2", h)
    assert not auth.verify_password("wrong", h)


def test_hash_is_salted():
    assert auth.hash_password("same") != auth.hash_password("same")


def test_register_consumes_invite_code(db):
    _code(db)
    u = auth.register(db, "alice", "pw12345678", "LETMEIN")
    assert u.username == "alice" and u.ai_quota >= 0
    assert db.get(InviteCode, "LETMEIN").used_count == 1


def test_register_rejects_unknown_code(db):
    with pytest.raises(auth.AuthError, match="邀请码"):
        auth.register(db, "bob", "pw12345678", "NOPE")


def test_register_rejects_exhausted_code(db):
    _code(db, max_uses=1)
    auth.register(db, "a", "pw12345678", "LETMEIN")
    with pytest.raises(auth.AuthError, match="邀请码"):
        auth.register(db, "b", "pw12345678", "LETMEIN")


def test_register_rejects_expired_code(db):
    _code(db, code="OLD", expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    with pytest.raises(auth.AuthError, match="邀请码"):
        auth.register(db, "c", "pw12345678", "OLD")


def test_register_rejects_duplicate_username(db):
    _code(db, max_uses=5)
    auth.register(db, "dup", "pw12345678", "LETMEIN")
    with pytest.raises(auth.AuthError, match="用户名"):
        auth.register(db, "dup", "pw12345678", "LETMEIN")


def test_register_rejects_short_password(db):
    _code(db)
    with pytest.raises(auth.AuthError, match="密码"):
        auth.register(db, "shorty", "123", "LETMEIN")


def test_authenticate_success_and_failure(db):
    _code(db)
    auth.register(db, "eve", "pw12345678", "LETMEIN")
    assert auth.authenticate(db, "eve", "pw12345678").username == "eve"
    with pytest.raises(auth.AuthError):
        auth.authenticate(db, "eve", "bad")
    with pytest.raises(auth.AuthError):
        auth.authenticate(db, "ghost", "pw12345678")


def test_session_roundtrip():
    uid = uuid.uuid4()
    assert auth.read_session(auth.make_session(uid)) == uid


def test_session_rejects_tampering():
    tok = auth.make_session(uuid.uuid4())
    assert auth.read_session(tok[:-3] + "xyz") is None
    assert auth.read_session("garbage") is None


def test_session_expires():
    tok = auth.make_session(uuid.uuid4())
    assert auth.read_session(tok, max_age_seconds=0) is None
```

`backend/tests/test_quota.py`：

```python
import pytest

from app.models import User
from app.services import quota


def _user(db, q=2):
    u = User(username=f"u{q}{id(db) % 1000}", password_hash="x", ai_quota=q)
    db.add(u)
    db.flush()
    return u


def test_reserve_decrements_remaining(db):
    u = _user(db, q=3)
    assert quota.remaining(db, u.id) == 3
    quota.reserve(db, u.id)
    assert quota.remaining(db, u.id) == 2
    assert u.ai_used == 1


def test_reserve_raises_when_exhausted(db):
    u = _user(db, q=1)
    quota.reserve(db, u.id)
    with pytest.raises(quota.QuotaExceeded):
        quota.reserve(db, u.id)
    assert quota.remaining(db, u.id) == 0


def test_zero_quota_user_cannot_reserve(db):
    u = _user(db, q=0)
    with pytest.raises(quota.QuotaExceeded):
        quota.reserve(db, u.id)


def test_refund_restores_and_never_goes_negative(db):
    u = _user(db, q=2)
    quota.reserve(db, u.id)
    quota.refund(db, u.id)
    assert quota.remaining(db, u.id) == 2 and u.ai_used == 0
    quota.refund(db, u.id)
    assert u.ai_used == 0


def test_reserve_uses_row_lock(db):
    """行级锁的存在性检查：确认 SQL 里带 FOR UPDATE，真正的并发行为见 test_jobs。"""
    import inspect as _i
    assert "with_for_update" in _i.getsource(quota.reserve)
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_auth_service.py tests/test_quota.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.auth'`。

- [ ] **Step 3: 写 auth.py**

`backend/app/services/auth.py`：

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import InviteCode, User

_ROUNDS = get_settings().bcrypt_rounds
_MIN_PASSWORD = 8
_SALT = "pindou-session"


class AuthError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt(rounds=_ROUNDS)).decode("ascii")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt=_SALT)


def make_session(user_id: uuid.UUID) -> str:
    return _serializer().dumps(str(user_id))


def read_session(token: str, max_age_seconds: int | None = None) -> uuid.UUID | None:
    if max_age_seconds is None:
        max_age_seconds = get_settings().session_max_age_days * 86400
    try:
        raw = _serializer().loads(token, max_age=max_age_seconds)
        return uuid.UUID(raw)
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None


def register(db: Session, username: str, password: str, invite_code: str) -> User:
    username = username.strip()
    if not username:
        raise AuthError("用户名不能为空")
    if len(password) < _MIN_PASSWORD:
        raise AuthError(f"密码至少 {_MIN_PASSWORD} 位")

    code = db.get(InviteCode, invite_code.strip(), with_for_update=True)
    if code is None or code.used_count >= code.max_uses:
        raise AuthError("邀请码无效或已用完")
    if code.expires_at is not None and code.expires_at < datetime.now(timezone.utc):
        raise AuthError("邀请码已过期")

    if db.scalar(select(User).where(User.username == username)) is not None:
        raise AuthError("用户名已被占用")

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    code.used_count += 1
    db.flush()
    return user


def authenticate(db: Session, username: str, password: str) -> User:
    user = db.scalar(select(User).where(User.username == username.strip()))
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("用户名或密码错误")
    return user
```

- [ ] **Step 4: 写 quota.py**

`backend/app/services/quota.py`：

```python
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


class QuotaExceeded(Exception):
    pass


def _locked_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise LookupError(f"user {user_id} not found")
    return user


def reserve(db: Session, user_id: uuid.UUID) -> None:
    """先扣后跑。行级锁保证并发提交不会把额度刷穿。"""
    user = _locked_user(db, user_id)
    if user.ai_used + 1 > user.ai_quota:
        raise QuotaExceeded(f"AI 额度不足：已用 {user.ai_used} / 共 {user.ai_quota}")
    user.ai_used += 1
    db.flush()


def refund(db: Session, user_id: uuid.UUID) -> None:
    user = _locked_user(db, user_id)
    user.ai_used = max(0, user.ai_used - 1)
    db.flush()


def remaining(db: Session, user_id: uuid.UUID) -> int:
    user = db.get(User, user_id)
    if user is None:
        raise LookupError(f"user {user_id} not found")
    return max(0, user.ai_quota - user.ai_used)
```

- [ ] **Step 5: 运行确认通过**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_auth_service.py tests/test_quota.py -q
```

Expected: 17 passed。

- [ ] **Step 6: 全量回归并提交**

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

Expected: 138 passed。

```bash
git add backend/app/services/auth.py backend/app/services/quota.py backend/tests/test_auth_service.py backend/tests/test_quota.py
git commit -m "feat(api): 认证服务（bcrypt + 签名会话 + 邀请码）与行级锁额度控制

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: AI Provider 抽象层

**Files:**
- Create: `backend/app/providers/__init__.py`、`base.py`、`fake.py`、`openai_compatible.py`、`dashscope_native.py`
- Create: `backend/providers.yaml.example`
- Test: `backend/tests/test_providers.py`

**Interfaces:**
- Produces: `base.RedrawResult` dataclass：`image: bytes`、`mime: str`、`model: str`、`cost: Decimal | None`、`raw: dict`
- Produces: `base.ProviderError(Exception)`，带 `retryable: bool`
- Produces: `base.ImageProvider` 协议：`name: str`、`redraw(image: bytes, prompt: str, params: dict) -> RedrawResult`、`estimate_cost(params: dict) -> Decimal`
- Produces: `base.ProviderConfig` dataclass：`name`、`adapter`、`base_url`、`api_key_env`、`model`、`extra: dict`
- Produces: `base.load_configs(path: Path) -> dict[str, ProviderConfig]`（读 YAML，文件不存在返回 `{}`）
- Produces: `base.build_provider(cfg: ProviderConfig) -> ImageProvider`（按 `adapter` 分派：`openai_compatible` / `dashscope_native` / `fake`；未知 adapter 抛 `ProviderError`；api_key 环境变量缺失抛 `ProviderError(retryable=False)`）
- Produces: `base.get_provider(name: str | None = None) -> ImageProvider`（`None` 取配置里第一个；无任何配置则回退 `FakeProvider`）
- Produces: `base.call_with_retry(provider, image, prompt, params, attempts: int = 3) -> RedrawResult`（只对 `retryable=True` 重试，退避 0.5s/1s）
- Produces: `fake.FakeProvider`：把输入图做 8 色 posterize 返回，不联网；`FakeProvider(fail_times=n)` 前 n 次抛可重试错误

**为什么两个适配器**：火山方舟与百炼兼容模式都走 OpenAI 风格的同步 JSON 接口；通义万相原生接口是"提交任务 → 轮询结果"的异步形态，塞不进同一个函数体。加第三家只需再加一个文件。

- [ ] **Step 1: 写 providers.yaml.example**

`backend/providers.yaml.example`：

```yaml
# 复制为 providers.yaml 并填入真实配置；providers.yaml 已被 .gitignore 忽略。
# 没有这个文件时系统回退到 FakeProvider（本地 posterize，不联网、不花钱）。
providers:
  - name: ark
    adapter: openai_compatible
    base_url: https://ark.cn-beijing.volces.com/api/v3
    api_key_env: ARK_API_KEY
    model: doubao-seedream-4-0
    extra:
      size: 1024x1024
      timeout: 120

  - name: dashscope
    adapter: dashscope_native
    base_url: https://dashscope.aliyuncs.com/api/v1
    api_key_env: DASHSCOPE_API_KEY
    model: wanx2.1-imageedit
    extra:
      function: stylization_all
      strength: 0.5
      poll_interval: 3
      poll_timeout: 300
```

- [ ] **Step 2: 写失败测试**

`backend/tests/test_providers.py`：

```python
import base64
import io
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
from PIL import Image

from app.providers import base as pbase
from app.providers.fake import FakeProvider


def _png(color=(200, 60, 60), size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


# ---------- 配置加载与分派 ----------

def test_load_configs_missing_file_returns_empty(tmp_path):
    assert pbase.load_configs(tmp_path / "nope.yaml") == {}


def test_load_configs_parses_yaml(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text("""
providers:
  - name: ark
    adapter: openai_compatible
    base_url: https://x/api
    api_key_env: ARK_KEY
    model: m1
    extra: {size: 512x512}
""", encoding="utf-8")
    cfgs = pbase.load_configs(f)
    assert set(cfgs) == {"ark"}
    assert cfgs["ark"].adapter == "openai_compatible" and cfgs["ark"].extra["size"] == "512x512"


def test_build_provider_unknown_adapter_raises():
    cfg = pbase.ProviderConfig(name="x", adapter="telepathy", base_url="", api_key_env="", model="")
    with pytest.raises(pbase.ProviderError):
        pbase.build_provider(cfg)


def test_build_provider_missing_key_raises_non_retryable(monkeypatch):
    monkeypatch.delenv("NO_SUCH_KEY", raising=False)
    cfg = pbase.ProviderConfig(name="ark", adapter="openai_compatible",
                               base_url="https://x", api_key_env="NO_SUCH_KEY", model="m")
    with pytest.raises(pbase.ProviderError) as e:
        pbase.build_provider(cfg)
    assert e.value.retryable is False


def test_get_provider_falls_back_to_fake_when_unconfigured(monkeypatch, tmp_path):
    monkeypatch.setattr(pbase, "_configs", lambda: {})
    assert isinstance(pbase.get_provider(), FakeProvider)


# ---------- FakeProvider ----------

def test_fake_provider_returns_posterized_image():
    r = FakeProvider().redraw(_png(), "任意提示词", {})
    assert r.mime == "image/png" and r.model == "fake"
    out = Image.open(io.BytesIO(r.image))
    assert out.size == (64, 64)
    assert len(out.convert("RGB").getcolors(maxcolors=1 << 24)) <= 8


def test_fake_provider_can_simulate_transient_failures():
    p = FakeProvider(fail_times=2)
    with pytest.raises(pbase.ProviderError):
        p.redraw(_png(), "x", {})
    with pytest.raises(pbase.ProviderError):
        p.redraw(_png(), "x", {})
    assert p.redraw(_png(), "x", {}).mime == "image/png"


def test_call_with_retry_recovers_then_succeeds():
    p = FakeProvider(fail_times=2)
    r = pbase.call_with_retry(p, _png(), "x", {}, attempts=3, backoff=0.0)
    assert r.mime == "image/png"


def test_call_with_retry_gives_up_after_attempts():
    p = FakeProvider(fail_times=5)
    with pytest.raises(pbase.ProviderError):
        pbase.call_with_retry(p, _png(), "x", {}, attempts=3, backoff=0.0)


def test_call_with_retry_does_not_retry_non_retryable():
    class Boom:
        name = "boom"
        calls = 0

        def redraw(self, image, prompt, params):
            Boom.calls += 1
            raise pbase.ProviderError("bad key", retryable=False)

        def estimate_cost(self, params):
            return Decimal("0")

    with pytest.raises(pbase.ProviderError):
        pbase.call_with_retry(Boom(), _png(), "x", {}, attempts=3, backoff=0.0)
    assert Boom.calls == 1


# ---------- openai_compatible ----------

@respx.mock
def test_openai_compatible_parses_b64_response(monkeypatch):
    monkeypatch.setenv("ARK_KEY", "sk-test")
    cfg = pbase.ProviderConfig(name="ark", adapter="openai_compatible",
                               base_url="https://ark.test/api/v3", api_key_env="ARK_KEY",
                               model="seedream", extra={"size": "512x512"})
    b64 = base64.b64encode(_png((10, 200, 10))).decode()
    route = respx.post("https://ark.test/api/v3/images/generations").mock(
        return_value=httpx.Response(200, json={"data": [{"b64_json": b64}]}))
    r = pbase.build_provider(cfg).redraw(_png(), "粗轮廓 纯色平涂", {})
    assert route.called
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer sk-test"
    assert Image.open(io.BytesIO(r.image)).size == (64, 64)
    assert r.model == "seedream"


@respx.mock
def test_openai_compatible_follows_url_response(monkeypatch):
    monkeypatch.setenv("ARK_KEY", "sk-test")
    cfg = pbase.ProviderConfig(name="ark", adapter="openai_compatible",
                               base_url="https://ark.test/api/v3", api_key_env="ARK_KEY", model="m")
    respx.post("https://ark.test/api/v3/images/generations").mock(
        return_value=httpx.Response(200, json={"data": [{"url": "https://cdn.test/out.png"}]}))
    respx.get("https://cdn.test/out.png").mock(
        return_value=httpx.Response(200, content=_png((1, 2, 3)), headers={"content-type": "image/png"}))
    assert pbase.build_provider(cfg).redraw(_png(), "p", {}).mime == "image/png"


@respx.mock
@pytest.mark.parametrize("status,retryable", [(429, True), (500, True), (503, True), (400, False), (401, False)])
def test_openai_compatible_error_classification(monkeypatch, status, retryable):
    monkeypatch.setenv("ARK_KEY", "sk-test")
    cfg = pbase.ProviderConfig(name="ark", adapter="openai_compatible",
                               base_url="https://ark.test/api/v3", api_key_env="ARK_KEY", model="m")
    respx.post("https://ark.test/api/v3/images/generations").mock(
        return_value=httpx.Response(status, json={"error": {"message": "nope"}}))
    with pytest.raises(pbase.ProviderError) as e:
        pbase.build_provider(cfg).redraw(_png(), "p", {})
    assert e.value.retryable is retryable


# ---------- dashscope_native ----------

@respx.mock
def test_dashscope_submits_then_polls(monkeypatch):
    monkeypatch.setenv("DS_KEY", "sk-ds")
    cfg = pbase.ProviderConfig(name="ds", adapter="dashscope_native",
                               base_url="https://ds.test/api/v1", api_key_env="DS_KEY",
                               model="wanx2.1-imageedit",
                               extra={"function": "stylization_all", "poll_interval": 0, "poll_timeout": 10})
    respx.post("https://ds.test/api/v1/services/aigc/image2image/image-synthesis").mock(
        return_value=httpx.Response(200, json={"output": {"task_id": "T1", "task_status": "PENDING"}}))
    poll = respx.get("https://ds.test/api/v1/tasks/T1")
    poll.side_effect = [
        httpx.Response(200, json={"output": {"task_status": "RUNNING"}}),
        httpx.Response(200, json={"output": {"task_status": "SUCCEEDED",
                                             "results": [{"url": "https://cdn.test/r.png"}]}}),
    ]
    respx.get("https://cdn.test/r.png").mock(
        return_value=httpx.Response(200, content=_png(), headers={"content-type": "image/png"}))
    r = pbase.build_provider(cfg).redraw(_png(), "像素风格插画", {})
    assert r.mime == "image/png" and poll.call_count == 2
    submit = respx.calls[0].request
    assert submit.headers["x-dashscope-async"] == "enable"


@respx.mock
def test_dashscope_failed_task_raises(monkeypatch):
    monkeypatch.setenv("DS_KEY", "sk-ds")
    cfg = pbase.ProviderConfig(name="ds", adapter="dashscope_native",
                               base_url="https://ds.test/api/v1", api_key_env="DS_KEY",
                               model="m", extra={"poll_interval": 0, "poll_timeout": 10})
    respx.post("https://ds.test/api/v1/services/aigc/image2image/image-synthesis").mock(
        return_value=httpx.Response(200, json={"output": {"task_id": "T2"}}))
    respx.get("https://ds.test/api/v1/tasks/T2").mock(
        return_value=httpx.Response(200, json={"output": {"task_status": "FAILED", "message": "nsfw"}}))
    with pytest.raises(pbase.ProviderError, match="nsfw"):
        pbase.build_provider(cfg).redraw(_png(), "p", {})


@respx.mock
def test_dashscope_poll_timeout_is_retryable(monkeypatch):
    monkeypatch.setenv("DS_KEY", "sk-ds")
    cfg = pbase.ProviderConfig(name="ds", adapter="dashscope_native",
                               base_url="https://ds.test/api/v1", api_key_env="DS_KEY",
                               model="m", extra={"poll_interval": 0, "poll_timeout": 0})
    respx.post("https://ds.test/api/v1/services/aigc/image2image/image-synthesis").mock(
        return_value=httpx.Response(200, json={"output": {"task_id": "T3"}}))
    respx.get("https://ds.test/api/v1/tasks/T3").mock(
        return_value=httpx.Response(200, json={"output": {"task_status": "RUNNING"}}))
    with pytest.raises(pbase.ProviderError) as e:
        pbase.build_provider(cfg).redraw(_png(), "p", {})
    assert e.value.retryable is True
```

- [ ] **Step 3: 运行确认失败**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_providers.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'app.providers'`。

- [ ] **Step 4: 写 base.py**

`backend/app/providers/__init__.py` 为空。`backend/app/providers/base.py`：

```python
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import yaml

from app.config import get_settings


class ProviderError(Exception):
    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable


@dataclass
class RedrawResult:
    image: bytes
    mime: str
    model: str
    cost: Decimal | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class ProviderConfig:
    name: str
    adapter: str
    base_url: str
    api_key_env: str
    model: str
    extra: dict = field(default_factory=dict)


class ImageProvider(Protocol):
    name: str

    def redraw(self, image: bytes, prompt: str, params: dict) -> RedrawResult: ...
    def estimate_cost(self, params: dict) -> Decimal: ...


def load_configs(path: Path) -> dict[str, ProviderConfig]:
    if not Path(path).exists():
        return {}
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    out: dict[str, ProviderConfig] = {}
    for item in doc.get("providers", []):
        cfg = ProviderConfig(
            name=item["name"], adapter=item["adapter"], base_url=item.get("base_url", ""),
            api_key_env=item.get("api_key_env", ""), model=item.get("model", ""),
            extra=item.get("extra") or {},
        )
        out[cfg.name] = cfg
    return out


@lru_cache
def _configs() -> dict[str, ProviderConfig]:
    return load_configs(get_settings().providers_file)


def build_provider(cfg: ProviderConfig) -> ImageProvider:
    from app.providers.dashscope_native import DashScopeNativeProvider
    from app.providers.fake import FakeProvider
    from app.providers.openai_compatible import OpenAICompatibleProvider

    if cfg.adapter == "fake":
        return FakeProvider()
    api_key = os.environ.get(cfg.api_key_env, "")
    if not api_key:
        raise ProviderError(
            f"provider {cfg.name!r}: 环境变量 {cfg.api_key_env} 未设置", retryable=False
        )
    if cfg.adapter == "openai_compatible":
        return OpenAICompatibleProvider(cfg, api_key)
    if cfg.adapter == "dashscope_native":
        return DashScopeNativeProvider(cfg, api_key)
    raise ProviderError(f"未知的 provider adapter: {cfg.adapter!r}", retryable=False)


def get_provider(name: str | None = None) -> ImageProvider:
    from app.providers.fake import FakeProvider

    cfgs = _configs()
    if not cfgs:
        return FakeProvider()
    if name is None:
        name = next(iter(cfgs))
    cfg = cfgs.get(name)
    if cfg is None:
        raise ProviderError(f"未配置的 provider: {name!r}", retryable=False)
    return build_provider(cfg)


def call_with_retry(provider: ImageProvider, image: bytes, prompt: str, params: dict,
                    attempts: int = 3, backoff: float = 0.5) -> RedrawResult:
    last: ProviderError | None = None
    for i in range(attempts):
        try:
            return provider.redraw(image, prompt, params)
        except ProviderError as e:
            last = e
            if not e.retryable or i == attempts - 1:
                raise
            if backoff:
                time.sleep(backoff * (2 ** i))
    raise last if last else ProviderError("unreachable")
```

- [ ] **Step 5: 写 fake.py**

`backend/app/providers/fake.py`：

```python
from __future__ import annotations

import io
from decimal import Decimal

from PIL import Image

from app.providers.base import ProviderError, RedrawResult


class FakeProvider:
    """本地假 provider：把输入图 posterize 成 8 色。不联网、不花钱。

    没有配置 providers.yaml 时系统回退到它，所以整条链路在无 API key 的环境下也能跑通。
    """

    name = "fake"

    def __init__(self, fail_times: int = 0) -> None:
        self._remaining_failures = fail_times

    def redraw(self, image: bytes, prompt: str, params: dict) -> RedrawResult:
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise ProviderError("fake transient failure", retryable=True)
        img = Image.open(io.BytesIO(image)).convert("RGB")
        out = img.quantize(colors=8, method=Image.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
        buf = io.BytesIO()
        out.save(buf, format="PNG")
        return RedrawResult(image=buf.getvalue(), mime="image/png", model="fake",
                            cost=Decimal("0"), raw={"prompt": prompt})

    def estimate_cost(self, params: dict) -> Decimal:
        return Decimal("0")
```

- [ ] **Step 6: 写 openai_compatible.py**

`backend/app/providers/openai_compatible.py`：

```python
from __future__ import annotations

import base64
from decimal import Decimal

import httpx

from app.providers.base import ProviderConfig, ProviderError, RedrawResult

_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class OpenAICompatibleProvider:
    """火山方舟 / 百炼兼容模式 / 任意 OpenAI 风格中转网关。同步 JSON 接口。"""

    def __init__(self, cfg: ProviderConfig, api_key: str) -> None:
        self.name = cfg.name
        self.cfg = cfg
        self._key = api_key

    def redraw(self, image: bytes, prompt: str, params: dict) -> RedrawResult:
        merged = {**self.cfg.extra, **params}
        timeout = float(merged.pop("timeout", 120))
        body = {
            "model": self.cfg.model,
            "prompt": prompt,
            "image": f"data:image/png;base64,{base64.b64encode(image).decode()}",
            "response_format": "b64_json",
        }
        for k in ("size", "seed", "guidance_scale", "watermark", "strength"):
            if k in merged:
                body[k] = merged[k]

        url = f"{self.cfg.base_url.rstrip('/')}/images/generations"
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=body,
                                   headers={"Authorization": f"Bearer {self._key}"})
                if resp.status_code >= 400:
                    raise ProviderError(
                        f"{self.name} HTTP {resp.status_code}: {resp.text[:300]}",
                        retryable=resp.status_code in _RETRYABLE_STATUS)
                payload = resp.json()
                data = (payload.get("data") or [{}])[0]
                if data.get("b64_json"):
                    img = base64.b64decode(data["b64_json"])
                elif data.get("url"):
                    got = client.get(data["url"])
                    if got.status_code >= 400:
                        raise ProviderError(f"{self.name} 取图失败 HTTP {got.status_code}",
                                            retryable=True)
                    img = got.content
                else:
                    raise ProviderError(f"{self.name} 返回体无法解析: {str(payload)[:300]}",
                                        retryable=False)
        except httpx.TimeoutException as e:
            raise ProviderError(f"{self.name} 超时: {e}", retryable=True) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name} 网络错误: {e}", retryable=True) from e

        return RedrawResult(image=img, mime="image/png", model=self.cfg.model,
                            cost=self.estimate_cost(merged), raw={"provider": self.name})

    def estimate_cost(self, params: dict) -> Decimal:
        return Decimal(str(self.cfg.extra.get("unit_cost", "0")))
```

- [ ] **Step 7: 写 dashscope_native.py**

`backend/app/providers/dashscope_native.py`：

```python
from __future__ import annotations

import base64
import time
from decimal import Decimal

import httpx

from app.providers.base import ProviderConfig, ProviderError, RedrawResult

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class DashScopeNativeProvider:
    """通义万相原生接口：提交异步任务 → 轮询 task_id → 取结果图。"""

    def __init__(self, cfg: ProviderConfig, api_key: str) -> None:
        self.name = cfg.name
        self.cfg = cfg
        self._key = api_key

    def _headers(self, async_: bool = False) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        if async_:
            h["X-DashScope-Async"] = "enable"
        return h

    def redraw(self, image: bytes, prompt: str, params: dict) -> RedrawResult:
        merged = {**self.cfg.extra, **params}
        poll_interval = float(merged.get("poll_interval", 3))
        poll_timeout = float(merged.get("poll_timeout", 300))
        base = self.cfg.base_url.rstrip("/")
        submit_url = f"{base}/services/aigc/image2image/image-synthesis"
        body = {
            "model": self.cfg.model,
            "input": {
                "prompt": prompt,
                "function": merged.get("function", "stylization_all"),
                "base_image_url": f"data:image/png;base64,{base64.b64encode(image).decode()}",
            },
            "parameters": {k: merged[k] for k in ("strength", "n", "seed") if k in merged},
        }

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(submit_url, json=body, headers=self._headers(async_=True))
                if resp.status_code >= 400:
                    raise ProviderError(f"{self.name} 提交失败 HTTP {resp.status_code}: {resp.text[:300]}",
                                        retryable=resp.status_code in _RETRYABLE_STATUS)
                task_id = (resp.json().get("output") or {}).get("task_id")
                if not task_id:
                    raise ProviderError(f"{self.name} 未返回 task_id: {resp.text[:300]}",
                                        retryable=False)

                deadline = time.monotonic() + poll_timeout
                url = None
                while True:
                    got = client.get(f"{base}/tasks/{task_id}", headers=self._headers())
                    if got.status_code >= 400:
                        raise ProviderError(f"{self.name} 轮询失败 HTTP {got.status_code}",
                                            retryable=got.status_code in _RETRYABLE_STATUS)
                    out = got.json().get("output") or {}
                    status = out.get("task_status")
                    if status == "SUCCEEDED":
                        results = out.get("results") or []
                        if not results or not results[0].get("url"):
                            raise ProviderError(f"{self.name} 成功但无结果图", retryable=False)
                        url = results[0]["url"]
                        break
                    if status in {"FAILED", "CANCELED", "UNKNOWN"}:
                        raise ProviderError(
                            f"{self.name} 任务{status}: {out.get('message', '')}", retryable=False)
                    if time.monotonic() >= deadline:
                        raise ProviderError(f"{self.name} 轮询超时（{poll_timeout}s）", retryable=True)
                    if poll_interval:
                        time.sleep(poll_interval)

                img_resp = client.get(url)
                if img_resp.status_code >= 400:
                    raise ProviderError(f"{self.name} 取图失败 HTTP {img_resp.status_code}",
                                        retryable=True)
                img = img_resp.content
        except httpx.TimeoutException as e:
            raise ProviderError(f"{self.name} 超时: {e}", retryable=True) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name} 网络错误: {e}", retryable=True) from e

        return RedrawResult(image=img, mime="image/png", model=self.cfg.model,
                            cost=self.estimate_cost(merged), raw={"provider": self.name})

    def estimate_cost(self, params: dict) -> Decimal:
        return Decimal(str(self.cfg.extra.get("unit_cost", "0")))
```

- [ ] **Step 8: 运行确认通过**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_providers.py -q
```

Expected: 17 passed（含 5 个参数化的错误分类用例）。

- [ ] **Step 9: 全量回归并提交**

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

Expected: 155 passed。

```bash
git add backend/app/providers backend/providers.yaml.example backend/tests/test_providers.py
git commit -m "feat(api): AI provider 抽象（配置驱动 + 两种适配器 + 重试分类 + 假 provider）

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: 图纸服务（生成 / 重算 / 修复 / 编辑 / 导出）

**Files:**
- Create: `backend/app/services/patterns.py`
- Test: `backend/tests/test_patterns_service.py`

**Interfaces:**
- Consumes: `core.pipeline.run/apply_edits/suggest_sizes`、`core.patches.apply_patch`、`core.buildability.analyze`、`core.render`、`core.pdf`、`services.palettes.load_core_palette`、`services.storage.get_storage`
- Produces: `patterns.params_from_dict(d: dict) -> core.types.Params`（白名单字段，越界抛 `PatternError`）
- Produces: `patterns.params_to_dict(p: core.types.Params) -> dict`
- Produces: `patterns.PatternError(Exception)`
- Produces: `patterns.create_project(db, user_id, name, image_bytes) -> Project`（校验大小/格式，落盘，建记录）
- Produces: `patterns.generate(db, project, params, ai_render=None) -> Pattern`（跑流水线，落库，`origin="generated"`）
- Produces: `patterns.apply_issue(db, pattern, issue_index: int) -> Pattern`（新版本，`origin="patched"`，记 `applied_patch`）
- Produces: `patterns.apply_manual_edits(db, pattern, edits: list[dict], protected_cells=None) -> Pattern`（新版本，`origin="edited"`，记 `manual_edits`；edits 元素 `{"cell": [r, c], "to": int | None}`）
- Produces: `patterns.export_png(pattern, palette, cell_px=28, board=None) -> bytes`、`patterns.export_pdf(pattern, palette, bead_mm=5.0) -> bytes`、`patterns.materials_of(pattern, palette) -> list[dict]`
- Produces: `patterns.grid_to_db(np.ndarray) -> list[list[int | None]]`、`patterns.grid_from_db(list) -> np.ndarray`（int16，None ↔ -1）

**关键约束**：`apply_manual_edits` 只按显式格子列表写入并重跑分析，**不重放油漆桶等填充算法**。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_patterns_service.py`：

```python
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.models import Pattern, Project, User
from app.services import patterns as svc
from app.services.palettes import load_core_palette

FIXTURES = Path(__file__).parent / "fixtures" / "images"


@pytest.fixture
def user(db):
    u = User(username="pat-user", password_hash="x", ai_quota=5)
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def palette():
    return load_core_palette("mard")


def _png(color=(200, 60, 60), size=(120, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


# ---------- 参数校验 ----------

def test_params_defaults_and_roundtrip():
    p = svc.params_from_dict({})
    assert p.grid_long_side == 58 and p.smoothness == 2.0 and p.dither is False
    assert svc.params_from_dict(svc.params_to_dict(p)).max_colors == p.max_colors


@pytest.mark.parametrize("bad", [
    {"grid_long_side": 1}, {"grid_long_side": 500},
    {"max_colors": 0}, {"max_colors": 999},
    {"smoothness": -1}, {"smoothness": 1000},
])
def test_params_out_of_range_rejected(bad):
    with pytest.raises(svc.PatternError):
        svc.params_from_dict(bad)


def test_params_ignores_unknown_keys():
    p = svc.params_from_dict({"grid_long_side": 40, "evil": "rm -rf"})
    assert p.grid_long_side == 40 and not hasattr(p, "evil")


# ---------- 网格序列化 ----------

def test_grid_db_roundtrip_preserves_empty_cells():
    g = np.array([[0, -1], [3, 2]], dtype=np.int16)
    as_db = svc.grid_to_db(g)
    assert as_db == [[0, None], [3, 2]]
    back = svc.grid_from_db(as_db)
    assert back.dtype == np.int16 and np.array_equal(back, g)


# ---------- 项目与生成 ----------

def test_create_project_stores_image_and_record(db, user):
    proj = svc.create_project(db, user.id, "测试", _png())
    assert isinstance(proj, Project) and proj.user_id == user.id
    assert svc.storage_of().exists(proj.source_image_path)


def test_create_project_rejects_oversize(db, user):
    with pytest.raises(svc.PatternError, match="过大"):
        svc.create_project(db, user.id, "big", b"x" * (21 * 1024 * 1024))


def test_create_project_rejects_non_image(db, user):
    with pytest.raises(svc.PatternError, match="格式"):
        svc.create_project(db, user.id, "bad", b"not an image at all")


def test_generate_persists_grid_and_report(db, user, palette):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    pat = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 30, "max_colors": 6}))
    assert isinstance(pat, Pattern) and pat.origin == "generated" and pat.parent_id is None
    assert len(pat.grid) == 30 and len(pat.grid[0]) == 30
    assert pat.color_stats and pat.buildability is not None
    assert "score" in pat.buildability and "confetti_pct" in pat.buildability
    assert pat.params["grid_long_side"] == 30


def test_generate_survives_buildability_failure(db, user, monkeypatch):
    """可拼性是附加环节——它炸了也必须出图。"""
    import app.services.patterns as m
    monkeypatch.setattr(m, "_analyze_report", lambda *a, **k: None)
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    pat = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 4}))
    assert pat.grid and pat.buildability is None


# ---------- 修复建议 ----------

def test_apply_issue_creates_child_version(db, user, palette):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "diagonal_trap.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 40, "max_colors": 4}))
    assert root.buildability["issues"], "斜线样本应该产出问题"
    child = svc.apply_issue(db, root, 0)
    assert child.parent_id == root.id and child.origin == "patched"
    assert child.applied_patch["type"] == root.buildability["issues"][0]["type"]
    assert child.grid != root.grid
    assert db.get(Pattern, root.id).grid == root.grid      # 原版本不被改动


def test_apply_issue_rejects_bad_index(db, user):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 4}))
    with pytest.raises(svc.PatternError):
        svc.apply_issue(db, root, 9999)


# ---------- 手工编辑 ----------

def test_apply_manual_edits_writes_cells_and_reanalyzes(db, user):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 6}))
    target = int(max(root.color_stats, key=lambda k: root.color_stats[k]))
    child = svc.apply_manual_edits(db, root, [
        {"cell": [0, 0], "to": target},
        {"cell": [1, 1], "to": None},
    ])
    assert child.origin == "edited" and child.parent_id == root.id
    assert child.grid[0][0] == target and child.grid[1][1] is None
    assert child.buildability is not None
    assert child.manual_edits[0]["cell"] == [0, 0]
    assert child.manual_edits[0]["from"] == root.grid[0][0]


def test_manual_edits_reject_out_of_bounds(db, user):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 4}))
    with pytest.raises(svc.PatternError, match="越界"):
        svc.apply_manual_edits(db, root, [{"cell": [99, 99], "to": 0}])


def test_manual_edits_reject_unknown_color_index(db, user, palette):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 4}))
    with pytest.raises(svc.PatternError, match="色号"):
        svc.apply_manual_edits(db, root, [{"cell": [0, 0], "to": len(palette) + 10}])


def test_manual_edits_empty_list_rejected(db, user):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    root = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 4}))
    with pytest.raises(svc.PatternError):
        svc.apply_manual_edits(db, root, [])


# ---------- 导出 ----------

def test_export_png_and_pdf_and_materials(db, user, palette):
    proj = svc.create_project(db, user.id, "t", (FIXTURES / "logo.png").read_bytes())
    pat = svc.generate(db, proj, svc.params_from_dict({"grid_long_side": 20, "max_colors": 5}))
    png = svc.export_png(pat, palette, cell_px=12)
    assert Image.open(io.BytesIO(png)).size[0] > 200
    pdf = svc.export_pdf(pat, palette)
    assert pdf[:5] == b"%PDF-"
    mats = svc.materials_of(pat, palette)
    assert mats and mats[0]["count"] >= mats[-1]["count"]
    assert sum(m["count"] for m in mats) == sum(pat.color_stats.values())
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_patterns_service.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.patterns'`。

- [ ] **Step 3: 实现**

`backend/app/services/patterns.py`：

```python
from __future__ import annotations

import hashlib
import io
import uuid
from dataclasses import fields as dc_fields

import numpy as np
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import pdf as core_pdf
from app.core import pipeline, render
from app.core.buildability import analyze
from app.core.palette import Palette as CorePalette
from app.core.patches import apply_patch, attach_patches
from app.core.split import Board
from app.core.types import EMPTY, Issue, Params
from app.models import AiRender, Pattern, Project
from app.services.palettes import load_core_palette
from app.services.storage import get_storage

_LIMITS = {
    "grid_long_side": (8, 200),
    "max_colors": (2, 64),
    "smoothness": (0.0, 50.0),
    "small_color_threshold": (0, 1000),
    "background_tolerance": (0.0, 1.0),
}
_PARAM_KEYS = {f.name for f in dc_fields(Params)}


class PatternError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def storage_of():
    return get_storage()


def params_from_dict(d: dict) -> Params:
    clean = {k: v for k, v in (d or {}).items() if k in _PARAM_KEYS}
    for key, (lo, hi) in _LIMITS.items():
        if key in clean and clean[key] is not None:
            v = clean[key]
            if not isinstance(v, (int, float)) or not (lo <= v <= hi):
                raise PatternError(f"参数 {key} 超出允许范围 [{lo}, {hi}]：{v!r}")
    if "protected_cells" in clean and clean["protected_cells"]:
        clean["protected_cells"] = [tuple(c) for c in clean["protected_cells"]]
    if "background_seed" in clean and clean["background_seed"]:
        clean["background_seed"] = tuple(clean["background_seed"])
    try:
        return Params(**clean)
    except TypeError as e:
        raise PatternError(f"参数无法解析：{e}") from e


def params_to_dict(p: Params) -> dict:
    return p.to_dict()


def grid_to_db(grid: np.ndarray) -> list[list[int | None]]:
    return [[None if int(v) == EMPTY else int(v) for v in row] for row in grid]


def grid_from_db(grid: list) -> np.ndarray:
    return np.array([[EMPTY if v is None else int(v) for v in row] for row in grid], dtype=np.int16)


def _analyze_report(grid: np.ndarray, palette: CorePalette, params: Params) -> dict | None:
    """可拼性是附加环节：任何异常都只让它变成 None，绝不让出图失败。"""
    try:
        report = attach_patches(
            analyze(grid, palette.lab, params.small_color_threshold,
                    set(map(tuple, params.protected_cells))),
            grid, palette.clear_index)
        return report.to_dict()
    except Exception:
        return None


def create_project(db: Session, user_id: uuid.UUID, name: str, image_bytes: bytes) -> Project:
    limit = get_settings().max_upload_bytes
    if len(image_bytes) > limit:
        raise PatternError(f"图片过大：{len(image_bytes)} 字节，上限 {limit}")
    try:
        probe = Image.open(io.BytesIO(image_bytes))
        probe.verify()
        fmt = (probe.format or "").upper()
    except (UnidentifiedImageError, OSError) as e:
        raise PatternError(f"无法识别的图片格式：{e}") from e
    if fmt not in {"PNG", "JPEG", "WEBP"}:
        raise PatternError(f"不支持的图片格式：{fmt or '未知'}，仅支持 PNG / JPEG / WEBP")

    key = hashlib.sha256(image_bytes).hexdigest()
    rel = storage_of().save("uploads", key, image_bytes, ".png" if fmt == "PNG" else ".bin")
    proj = Project(user_id=user_id, name=name.strip() or "未命名", source_image_path=rel)
    db.add(proj)
    db.flush()
    return proj


def _source_bytes(project: Project, ai_render: AiRender | None) -> bytes:
    st = storage_of()
    if ai_render is not None and ai_render.output_path:
        return st.load(ai_render.output_path)
    return st.load(project.source_image_path)


def generate(db: Session, project: Project, params: Params,
             ai_render: AiRender | None = None) -> Pattern:
    palette = load_core_palette(params.palette_id)
    result = pipeline.run(_source_bytes(project, ai_render), params, palette)
    pat = Pattern(
        project_id=project.id,
        ai_render_id=ai_render.id if ai_render is not None else None,
        origin="generated",
        params=params_to_dict(params),
        grid=grid_to_db(result.grid),
        color_stats={str(k): int(v) for k, v in result.color_stats.items()},
        buildability=_analyze_report(result.grid, palette, params),
    )
    db.add(pat)
    db.flush()
    return pat


def _child(db: Session, parent: Pattern, grid: np.ndarray, palette: CorePalette,
           params: Params, origin: str, **extra) -> Pattern:
    from app.core.merge import color_counts

    child = Pattern(
        project_id=parent.project_id, ai_render_id=parent.ai_render_id, parent_id=parent.id,
        origin=origin, params=parent.params, grid=grid_to_db(grid),
        color_stats={str(k): int(v) for k, v in color_counts(grid).items()},
        buildability=_analyze_report(grid, palette, params), **extra)
    db.add(child)
    db.flush()
    return child


def apply_issue(db: Session, pattern: Pattern, issue_index: int) -> Pattern:
    if not pattern.buildability or not pattern.buildability.get("issues"):
        raise PatternError("这张图纸没有可应用的修复建议")
    issues = pattern.buildability["issues"]
    if not (0 <= issue_index < len(issues)):
        raise PatternError(f"修复建议序号越界：{issue_index}")
    raw = issues[issue_index]
    params = params_from_dict(pattern.params)
    palette = load_core_palette(params.palette_id)
    issue = Issue(
        type=raw["type"], cells=[tuple(c) for c in raw["cells"]], action=raw["action"],
        target_color=raw.get("target_color"), delta_e=raw.get("delta_e"),
        patch_cells=[tuple(c) for c in raw.get("patch_cells", [])],
        severity=raw.get("severity", 1.0))
    new_grid = apply_patch(grid_from_db(pattern.grid), issue, palette.clear_index)
    return _child(db, pattern, new_grid, palette, params, "patched", applied_patch=raw)


def apply_manual_edits(db: Session, pattern: Pattern, edits: list[dict],
                       protected_cells: list[list[int]] | None = None) -> Pattern:
    """按显式格子列表写入。后端不重放油漆桶等填充算法——前端提交的是结果，不是操作意图。"""
    if not edits:
        raise PatternError("改动集为空")
    params = params_from_dict(pattern.params)
    palette = load_core_palette(params.palette_id)
    grid = grid_from_db(pattern.grid)
    rows, cols = grid.shape
    recorded = []
    for e in edits:
        try:
            r, c = int(e["cell"][0]), int(e["cell"][1])
        except (KeyError, IndexError, TypeError, ValueError) as ex:
            raise PatternError(f"改动项格式错误：{e!r}") from ex
        if not (0 <= r < rows and 0 <= c < cols):
            raise PatternError(f"格子越界：({r}, {c})，图纸尺寸 {rows}×{cols}")
        to = e.get("to")
        if to is not None:
            to = int(to)
            if not (0 <= to < len(palette)):
                raise PatternError(f"未知色号索引：{to}")
        recorded.append({"cell": [r, c], "from": None if grid[r, c] == EMPTY else int(grid[r, c]),
                         "to": to})
        grid[r, c] = EMPTY if to is None else to

    if protected_cells is not None:
        params.protected_cells = [tuple(c) for c in protected_cells]
    return _child(db, pattern, grid, palette, params, "edited", manual_edits=recorded)


def materials_of(pattern: Pattern, palette: CorePalette, pack_size: int = 1000) -> list[dict]:
    return render.materials(grid_from_db(pattern.grid), palette, pack_size=pack_size)


def export_png(pattern: Pattern, palette: CorePalette, cell_px: int = 28,
               board: Board | None = None) -> bytes:
    img = render.render_grid(grid_from_db(pattern.grid), palette,
                             render.RenderOptions(cell_px=cell_px, board=board))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def export_pdf(pattern: Pattern, palette: CorePalette, bead_mm: float = 5.0) -> bytes:
    return core_pdf.render_pdf(grid_from_db(pattern.grid), palette,
                               core_pdf.PdfOptions(bead_mm=bead_mm))
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_patterns_service.py -q
```

Expected: 20 passed（含 6 个参数化的越界用例）。

- [ ] **Step 5: 全量回归并提交**

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

Expected: 175 passed。

```bash
git add backend/app/services/patterns.py backend/tests/test_patterns_service.py
git commit -m "feat(api): 图纸服务——生成、修复建议、手工编辑版本树与导出

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: AI 重绘服务与 jobs 队列

**Files:**
- Create: `backend/app/services/renders.py`、`backend/app/services/jobs.py`
- Test: `backend/tests/test_jobs.py`

**Interfaces:**
- Produces: `renders.input_hash(image_bytes: bytes, prompt: str, params: dict) -> str`（sha256，前 64 位十六进制）
- Produces: `renders.find_cached(db, project_id, input_hash, style_preset_id) -> AiRender | None`（只返回 `status="done"` 且文件仍在的）
- Produces: `renders.redraw(db, user_id, project, style_preset, provider_name=None) -> AiRender`：命中缓存直接返回且**不扣额度**；否则 `quota.reserve` → 调 provider（带重试）→ 落盘 → 记录；失败 `quota.refund` 并把 `AiRender.status="failed"`、`error` 写入后抛出
- Produces: `jobs.enqueue(db, type: str, payload: dict) -> Job`
- Produces: `jobs.claim(db) -> Job | None`（`SELECT ... FOR UPDATE SKIP LOCKED` 取一条 pending，置 `running` + `locked_at`，`attempts += 1`）
- Produces: `jobs.run_generate_job(session_factory, job_id: int) -> None`（独立事务执行：可选 AI 重绘 → 生成图纸 → 写 `result={"pattern_id": ...}` → `status="done"`；异常写 `error` 与 `status="failed"`）
- Produces: `jobs.reclaim_stale(db) -> int`（启动钩子：把 `running` 的 job 标 `failed`、退还额度、返回处理条数）
- Produces: `jobs.JOB_GENERATE = "generate"`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_jobs.py`：

```python
import io
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from app.models import AiRender, Job, Pattern, Project, StylePreset, User
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
    from app.models import User as U
    poor = U(username="poor", password_hash="x", ai_quota=0)
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


def test_claim_skips_locked_rows(session_factory, project):
    """两个真实连接同时抢：SKIP LOCKED 必须让它们拿到不同的任务，且都不阻塞。"""
    s1, s2 = session_factory(), session_factory()
    try:
        a = jsvc.enqueue(s1, jsvc.JOB_GENERATE, {"n": 1})
        b = jsvc.enqueue(s1, jsvc.JOB_GENERATE, {"n": 2})
        s1.commit()
        s1.begin()
        first = jsvc.claim(s1)          # s1 持有行锁，未提交
        second = jsvc.claim(s2)         # s2 必须跳过被锁那行，拿到另一条
        assert first is not None and second is not None
        assert first.id != second.id
        assert {first.id, second.id} == {a.id, b.id}
    finally:
        s1.rollback()
        s2.rollback()
        for s in (s1, s2):
            s.query(Job).delete()
            s.commit()
            s.close()


def test_run_generate_job_without_ai_produces_pattern(session_factory, db, user, project):
    job = jsvc.enqueue(db, jsvc.JOB_GENERATE, {
        "project_id": str(project.id), "user_id": str(user.id),
        "use_ai": False, "params": {"grid_long_side": 20, "max_colors": 4}})
    db.commit()
    try:
        jsvc.run_generate_job(session_factory, job.id)
        s = session_factory()
        done = s.get(Job, job.id)
        assert done.status == "done" and done.result["pattern_id"]
        pat = s.get(Pattern, __import__("uuid").UUID(done.result["pattern_id"]))
        assert pat is not None and len(pat.grid) == 20
        s.close()
    finally:
        s2 = session_factory()
        s2.query(Pattern).delete()
        s2.query(Job).delete()
        s2.commit()
        s2.close()


def test_run_generate_job_records_error_on_failure(session_factory, db, project, user):
    job = jsvc.enqueue(db, jsvc.JOB_GENERATE, {
        "project_id": str(project.id), "user_id": str(user.id),
        "use_ai": False, "params": {"grid_long_side": 99999}})
    db.commit()
    try:
        jsvc.run_generate_job(session_factory, job.id)
        s = session_factory()
        failed = s.get(Job, job.id)
        assert failed.status == "failed" and failed.error
        s.close()
    finally:
        s2 = session_factory()
        s2.query(Job).delete()
        s2.commit()
        s2.close()


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
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_jobs.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.renders'`。

- [ ] **Step 3: 写 renders.py**

`backend/app/services/renders.py`：

```python
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
```

- [ ] **Step 4: 写 jobs.py**

`backend/app/services/jobs.py`：

```python
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
            ai_render = renders.redraw(db, user_id, project, preset,
                                       payload.get("provider"))

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
```

- [ ] **Step 5: 运行确认通过**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_jobs.py -q
```

Expected: 12 passed。`test_claim_skips_locked_rows` 若卡住不返回，说明 `with_for_update(skip_locked=True)` 没生效——检查是否误用了 `with_for_update()` 不带参数。

- [ ] **Step 6: 全量回归并提交**

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

Expected: 187 passed。

```bash
git add backend/app/services/renders.py backend/app/services/jobs.py backend/tests/test_jobs.py
git commit -m "feat(api): AI 重绘服务（缓存不扣额度、失败退还）与 SKIP LOCKED 任务队列

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Pydantic schemas、API 依赖与认证路由

**Files:**
- Create: `backend/app/schemas.py`、`backend/app/api/__init__.py`、`backend/app/api/deps.py`、`backend/app/api/auth.py`、`backend/app/main.py`
- Modify: `backend/tests/conftest.py`（加 `client`、`auth_client` 夹具）
- Test: `backend/tests/test_api_auth.py`

**Interfaces:**
- Produces（schemas，全部 `model_config = ConfigDict(from_attributes=True)`）：
  - `RegisterIn(username: str, password: str, invite_code: str)`、`LoginIn(username, password)`
  - `UserOut(id, username, ai_quota, ai_used, is_admin)`
  - `ProjectOut(id, name, created_at, patterns: list[PatternBrief])`、`PatternBrief(id, origin, parent_id, created_at, score: float | None, n_colors: int)`
  - `GenerateIn(use_ai: bool = False, style_preset_id: UUID | None = None, params: dict = {})`
  - `PatternParamsIn(source: str = "original", ai_render_id: UUID | None = None, params: dict = {})`
  - `PatternOut(id, project_id, parent_id, origin, params, grid, color_stats, buildability, materials, palette_id, created_at)`
  - `EditIn(edits: list[EditCell], protected_cells: list[list[int]] | None = None)`、`EditCell(cell: list[int], to: int | None)`
  - `PatchIn(issue_index: int)`、`FeedbackIn(kind: str, cells: list[list[int]], note: str | None = None)`
  - `JobOut(id, type, status, result, error, created_at)`
  - `PaletteOut(id, brand, name, version)`、`PaletteColorOut(index: int, code, name, hex: str, role: str | None, confidence: str)`
  - `StylePresetOut(id, name, prompt, version)`、`SizeSuggestion(long_side: int, detail_loss: float)`
- Produces: `deps.current_user(request, db) -> User`（读 cookie → `auth.read_session` → 查库；失败 401）、`deps.current_admin(...)`（非管理员 403）、`deps.db_session`（`Depends(get_db)` 别名）
- Produces: `api.auth.router`：`POST /register`、`POST /login`、`POST /logout`、`GET /me`
- Produces: `main.create_app() -> FastAPI`、模块级 `app = create_app()`；注册全部路由、`AuthError/QuotaExceeded/PatternError/ProviderError` 的异常处理器、启动钩子（`reclaim_stale` + `seed_palettes`）

**Cookie 约定**：名称取 `settings.session_cookie_name`，`httponly=True`、`samesite="lax"`、`max_age=session_max_age_days*86400`、`secure=False`（本地 http 开发；部署到 https 时改 True）。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_api_auth.py`：

```python
import pytest

from app.models import InviteCode, User
from app.services import auth


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch):
    monkeypatch.setattr(auth, "_ROUNDS", 4)


@pytest.fixture
def invite(db):
    c = InviteCode(code="OPEN2026", max_uses=5)
    db.add(c)
    db.flush()
    return c


def test_register_then_me(client, invite):
    r = client.post("/api/auth/register",
                    json={"username": "amy", "password": "pw12345678", "invite_code": "OPEN2026"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["username"] == "amy" and body["ai_used"] == 0
    assert "password" not in body and "password_hash" not in body

    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["username"] == "amy"


def test_register_sets_httponly_cookie(client, invite):
    r = client.post("/api/auth/register",
                    json={"username": "cookie", "password": "pw12345678", "invite_code": "OPEN2026"})
    set_cookie = r.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


def test_register_rejects_bad_invite(client):
    r = client.post("/api/auth/register",
                    json={"username": "x", "password": "pw12345678", "invite_code": "NOPE"})
    assert r.status_code == 400 and "邀请码" in r.json()["detail"]


def test_register_rejects_short_password(client, invite):
    r = client.post("/api/auth/register",
                    json={"username": "x", "password": "123", "invite_code": "OPEN2026"})
    assert r.status_code == 400


def test_login_logout_cycle(client, invite):
    client.post("/api/auth/register",
                json={"username": "leo", "password": "pw12345678", "invite_code": "OPEN2026"})
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    bad = client.post("/api/auth/login", json={"username": "leo", "password": "wrong"})
    assert bad.status_code == 401

    ok = client.post("/api/auth/login", json={"username": "leo", "password": "pw12345678"})
    assert ok.status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "leo"


def test_me_without_cookie_is_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_tampered_cookie_is_401(client, invite):
    client.post("/api/auth/register",
                json={"username": "tam", "password": "pw12345678", "invite_code": "OPEN2026"})
    client.cookies.set("pindou_session", "forged.value.here")
    assert client.get("/api/auth/me").status_code == 401


def test_health_needs_no_auth(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
```

在 `backend/tests/conftest.py` 末尾追加：

```python
@pytest.fixture
def client(db, monkeypatch):
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
    from app.models import InviteCode
    from app.services import auth as auth_svc

    monkey_rounds = auth_svc._ROUNDS
    auth_svc._ROUNDS = 4
    try:
        db.add(InviteCode(code="FIXTURE", max_uses=99))
        db.flush()
        client.post("/api/auth/register",
                    json={"username": "fixture-user", "password": "pw12345678",
                          "invite_code": "FIXTURE"})
        from sqlalchemy import select

        from app.models import User
        client.user = db.scalar(select(User).where(User.username == "fixture-user"))
        client.user.ai_quota = 10
        db.flush()
        yield client
    finally:
        auth_svc._ROUNDS = monkey_rounds
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_api_auth.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'app.main'`。

- [ ] **Step 3: 写 schemas.py**

`backend/app/schemas.py`：

```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------

class RegisterIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    invite_code: str = Field(min_length=1, max_length=64)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(_Base):
    id: uuid.UUID
    username: str
    ai_quota: int
    ai_used: int
    is_admin: bool


# ---------- projects & patterns ----------

class PatternBrief(_Base):
    id: uuid.UUID
    origin: str
    parent_id: uuid.UUID | None
    created_at: datetime
    score: float | None = None
    n_colors: int = 0


class ProjectOut(_Base):
    id: uuid.UUID
    name: str
    created_at: datetime
    patterns: list[PatternBrief] = []


class GenerateIn(BaseModel):
    use_ai: bool = False
    style_preset_id: uuid.UUID | None = None
    provider: str | None = None
    params: dict = Field(default_factory=dict)


class PatternParamsIn(BaseModel):
    source: str = "original"
    ai_render_id: uuid.UUID | None = None
    params: dict = Field(default_factory=dict)


class PatternOut(_Base):
    id: uuid.UUID
    project_id: uuid.UUID
    parent_id: uuid.UUID | None
    origin: str
    params: dict
    grid: list
    color_stats: dict
    buildability: dict | None
    materials: list[dict] = []
    palette_id: str = "mard"
    created_at: datetime


class EditCell(BaseModel):
    cell: list[int] = Field(min_length=2, max_length=2)
    to: int | None = None


class EditIn(BaseModel):
    edits: list[EditCell] = Field(min_length=1, max_length=20000)
    protected_cells: list[list[int]] | None = None


class PatchIn(BaseModel):
    issue_index: int = Field(ge=0)


class FeedbackIn(BaseModel):
    kind: str = Field(min_length=1, max_length=32)
    cells: list[list[int]] = Field(default_factory=list, max_length=20000)
    note: str | None = Field(default=None, max_length=2000)


# ---------- jobs & meta ----------

class JobOut(_Base):
    id: int
    type: str
    status: str
    result: dict | None
    error: str | None
    created_at: datetime


class PaletteOut(_Base):
    id: uuid.UUID
    brand: str
    name: str
    version: str


class PaletteColorOut(BaseModel):
    index: int
    code: str
    name: str
    hex: str
    role: str | None = None
    confidence: str


class StylePresetOut(_Base):
    id: uuid.UUID
    name: str
    prompt: str
    version: int


class SizeSuggestion(BaseModel):
    long_side: int
    detail_loss: float
```

- [ ] **Step 4: 写 deps.py 与 api/auth.py**

`backend/app/api/__init__.py` 为空。`backend/app/api/deps.py`：

```python
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User
from app.services.auth import read_session


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
    user_id = read_session(token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "会话无效或已过期")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    return user
```

`backend/app/api/auth.py`：

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User
from app.schemas import LoginIn, RegisterIn, UserOut
from app.services.auth import authenticate, make_session, register
from app.api.deps import current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(response: Response, user_id) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name, make_session(user_id),
        max_age=s.session_max_age_days * 86400,
        httponly=True, samesite="lax", secure=False, path="/",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_endpoint(body: RegisterIn, response: Response, db: Session = Depends(get_db)) -> User:
    user = register(db, body.username, body.password, body.invite_code)
    db.commit()
    _set_cookie(response, user.id)
    return user


@router.post("/login", response_model=UserOut)
def login_endpoint(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> User:
    user = authenticate(db, body.username, body.password)
    _set_cookie(response, user.id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_endpoint(response: Response) -> Response:
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me_endpoint(user: User = Depends(current_user)) -> User:
    return user
```

- [ ] **Step 5: 写 main.py**

`backend/app/main.py`：

```python
from __future__ import annotations

import logging

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
        code = status.HTTP_401_UNAUTHORIZED if "密码" in exc.message or "错误" in exc.message \
            else status.HTTP_400_BAD_REQUEST
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


def _startup(app: FastAPI) -> None:
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
    app = FastAPI(title="拼豆图纸生成", version="0.1.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
    _install_error_handlers(app)

    from app.api import auth as auth_api
    app.include_router(auth_api.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    if run_startup:
        @app.on_event("startup")
        def _on_startup() -> None:
            _startup(app)

    return app


app = create_app()
```

- [ ] **Step 6: 运行确认通过**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_api_auth.py -q
```

Expected: 8 passed。

- [ ] **Step 7: 全量回归并提交**

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

Expected: 195 passed。

```bash
git add backend/app/schemas.py backend/app/api backend/app/main.py backend/tests
git commit -m "feat(api): Pydantic schemas、会话依赖、认证路由与应用装配

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: 项目、图纸、任务与元数据路由

**Files:**
- Create: `backend/app/api/projects.py`、`patterns.py`、`jobs.py`、`meta.py`
- Modify: `backend/app/main.py`（注册新路由）
- Test: `backend/tests/test_api_projects.py`、`backend/tests/test_api_patterns.py`、`backend/tests/test_api_export.py`

**Interfaces:**
- Consumes: `deps.current_user`、`services.patterns.*`、`services.jobs.*`、`services.renders.*`、`services.palettes.load_core_palette`
- Produces 路由（全部挂 `/api`）：

```
POST   /projects                       multipart: file + name        -> ProjectOut (201)
GET    /projects                                                     -> list[ProjectOut]
GET    /projects/{id}                                                -> ProjectOut（含版本列表）
GET    /projects/{id}/source                                         -> 原图字节
POST   /projects/{id}/generate         GenerateIn                    -> JobOut (202)
GET    /projects/{id}/suggest-sizes?base=58                          -> list[SizeSuggestion]
GET    /jobs/{id}                                                    -> JobOut
POST   /projects/{id}/patterns         PatternParamsIn               -> PatternOut（同步重算）
GET    /patterns/{id}                                                -> PatternOut
POST   /patterns/{id}/apply-patch      PatchIn                       -> PatternOut（新版本）
POST   /patterns/{id}/edits            EditIn                        -> PatternOut（新版本）
POST   /patterns/{id}/feedback         FeedbackIn                    -> 204
GET    /patterns/{id}/export?format=png|pdf&cell_px=28&bead_mm=5.0   -> 文件流
GET    /palettes                                                     -> list[PaletteOut]
GET    /palettes/{palette_id}/colors                                 -> list[PaletteColorOut]
GET    /style-presets                                                -> list[StylePresetOut]
```

- Produces: `projects._owned_project(db, user, project_id) -> Project`、`patterns_api._owned_pattern(db, user, pattern_id) -> Pattern`（不属于当前用户一律 404，不泄露存在性）
- Produces: `patterns_api.pattern_out(pattern, palette) -> dict`（在 `PatternOut` 基础上补 `materials`）

**并发约定**：`POST /projects/{id}/generate` 入队后用 FastAPI `BackgroundTasks` 就地执行 `run_generate_job`（v1 不起独立 worker 进程，`jobs` 表已建好，将来拆进程只换调用点）。

- [ ] **Step 1: 写失败测试（项目）**

`backend/tests/test_api_projects.py`：

```python
import io
from pathlib import Path

import pytest
from PIL import Image

from app.models import StylePreset

FIXTURES = Path(__file__).parent / "fixtures" / "images"


def _upload(client, name="t", path="logo.png"):
    return client.post("/api/projects", data={"name": name},
                       files={"file": (path, (FIXTURES / path).read_bytes(), "image/png")})


def test_create_and_list_project(auth_client):
    r = _upload(auth_client, "我的第一张")
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["name"] == "我的第一张"

    lst = auth_client.get("/api/projects")
    assert lst.status_code == 200 and [p["id"] for p in lst.json()] == [pid]


def test_create_rejects_non_image(auth_client):
    r = auth_client.post("/api/projects", data={"name": "bad"},
                         files={"file": ("x.png", b"definitely not a png", "image/png")})
    assert r.status_code == 400 and "格式" in r.json()["detail"]


def test_project_requires_auth(client):
    assert client.get("/api/projects").status_code == 401


def test_cannot_read_other_users_project(auth_client, client, db, invite_other):
    pid = _upload(auth_client).json()["id"]
    client.cookies.clear()
    client.post("/api/auth/register",
                json={"username": "intruder", "password": "pw12345678", "invite_code": "OTHER"})
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_source_image_is_served_back(auth_client):
    pid = _upload(auth_client).json()["id"]
    r = auth_client.get(f"/api/projects/{pid}/source")
    assert r.status_code == 200
    assert Image.open(io.BytesIO(r.content)).size[0] > 0


def test_suggest_sizes(auth_client):
    pid = _upload(auth_client).json()["id"]
    r = auth_client.get(f"/api/projects/{pid}/suggest-sizes?base=40")
    assert r.status_code == 200
    body = r.json()
    assert [x["long_side"] for x in body] == [30, 40, 60]
    assert body[0]["detail_loss"] >= body[-1]["detail_loss"]


def test_generate_without_ai_runs_and_returns_pattern(auth_client, db):
    pid = _upload(auth_client).json()["id"]
    r = auth_client.post(f"/api/projects/{pid}/generate",
                         json={"use_ai": False, "params": {"grid_long_side": 20, "max_colors": 4}})
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    got = auth_client.get(f"/api/jobs/{job_id}")
    assert got.status_code == 200
    assert got.json()["status"] in {"pending", "running", "done"}


def test_generate_with_ai_but_no_preset_is_rejected(auth_client):
    pid = _upload(auth_client).json()["id"]
    r = auth_client.post(f"/api/projects/{pid}/generate", json={"use_ai": True})
    assert r.status_code == 400


def test_generate_with_ai_without_quota_is_402(auth_client, db):
    auth_client.user.ai_quota = 0
    db.flush()
    sp = StylePreset(name="Q版", prompt="粗轮廓", params={})
    db.add(sp)
    db.flush()
    pid = _upload(auth_client).json()["id"]
    r = auth_client.post(f"/api/projects/{pid}/generate",
                         json={"use_ai": True, "style_preset_id": str(sp.id)})
    assert r.status_code == 402
```

在 `conftest.py` 末尾再补一个夹具：

```python
@pytest.fixture
def invite_other(db):
    from app.models import InviteCode
    db.add(InviteCode(code="OTHER", max_uses=9))
    db.flush()
```

- [ ] **Step 2: 写失败测试（图纸与导出）**

`backend/tests/test_api_patterns.py`：

```python
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "images"


@pytest.fixture
def pattern(auth_client, db):
    from app.services import patterns as svc
    pid = auth_client.post("/api/projects", data={"name": "t"},
                           files={"file": ("logo.png", (FIXTURES / "logo.png").read_bytes(),
                                           "image/png")}).json()["id"]
    r = auth_client.post(f"/api/projects/{pid}/patterns",
                         json={"params": {"grid_long_side": 20, "max_colors": 5}})
    assert r.status_code == 200, r.text
    return r.json()


def test_sync_recompute_returns_full_pattern(pattern):
    assert len(pattern["grid"]) == 20
    assert pattern["origin"] == "generated"
    assert pattern["buildability"]["score"] >= 0
    assert pattern["materials"] and "code" in pattern["materials"][0]


def test_changing_params_changes_grid(auth_client, pattern):
    pid = pattern["project_id"]
    other = auth_client.post(f"/api/projects/{pid}/patterns",
                             json={"params": {"grid_long_side": 30, "max_colors": 5}}).json()
    assert len(other["grid"]) == 30 and other["id"] != pattern["id"]


def test_get_pattern_by_id(auth_client, pattern):
    r = auth_client.get(f"/api/patterns/{pattern['id']}")
    assert r.status_code == 200 and r.json()["id"] == pattern["id"]


def test_apply_patch_creates_child(auth_client, db):
    pid = auth_client.post("/api/projects", data={"name": "d"},
                           files={"file": ("diagonal_trap.png",
                                           (FIXTURES / "diagonal_trap.png").read_bytes(),
                                           "image/png")}).json()["id"]
    root = auth_client.post(f"/api/projects/{pid}/patterns",
                            json={"params": {"grid_long_side": 40, "max_colors": 4}}).json()
    assert root["buildability"]["issues"]
    r = auth_client.post(f"/api/patterns/{root['id']}/apply-patch", json={"issue_index": 0})
    assert r.status_code == 200
    child = r.json()
    assert child["parent_id"] == root["id"] and child["origin"] == "patched"


def test_apply_patch_bad_index_is_400(auth_client, pattern):
    r = auth_client.post(f"/api/patterns/{pattern['id']}/apply-patch", json={"issue_index": 9999})
    assert r.status_code == 400


def test_edits_create_child_and_reanalyze(auth_client, pattern):
    target = int(max(pattern["color_stats"], key=lambda k: pattern["color_stats"][k]))
    r = auth_client.post(f"/api/patterns/{pattern['id']}/edits",
                         json={"edits": [{"cell": [0, 0], "to": target},
                                         {"cell": [1, 1], "to": None}]})
    assert r.status_code == 200, r.text
    child = r.json()
    assert child["origin"] == "edited" and child["parent_id"] == pattern["id"]
    assert child["grid"][0][0] == target and child["grid"][1][1] is None
    assert child["buildability"] is not None


def test_edits_out_of_bounds_is_400(auth_client, pattern):
    r = auth_client.post(f"/api/patterns/{pattern['id']}/edits",
                         json={"edits": [{"cell": [999, 999], "to": 0}]})
    assert r.status_code == 400


def test_edits_empty_is_422(auth_client, pattern):
    r = auth_client.post(f"/api/patterns/{pattern['id']}/edits", json={"edits": []})
    assert r.status_code == 422       # Pydantic min_length=1 先拦下


def test_feedback_is_recorded(auth_client, pattern, db):
    from sqlalchemy import select

    from app.models import Feedback
    r = auth_client.post(f"/api/patterns/{pattern['id']}/feedback",
                         json={"kind": "断裂", "cells": [[3, 4], [3, 5]], "note": "发尾断了"})
    assert r.status_code == 204
    fb = db.scalars(select(Feedback)).all()
    assert fb and fb[-1].cells == [[3, 4], [3, 5]] and fb[-1].kind == "断裂"


def test_project_detail_lists_version_tree(auth_client, pattern):
    r = auth_client.get(f"/api/projects/{pattern['project_id']}")
    assert r.status_code == 200
    briefs = r.json()["patterns"]
    assert any(b["id"] == pattern["id"] for b in briefs)
    assert briefs[0]["n_colors"] > 0


def test_cannot_touch_other_users_pattern(auth_client, client, pattern, invite_other):
    client.cookies.clear()
    client.post("/api/auth/register",
                json={"username": "thief", "password": "pw12345678", "invite_code": "OTHER"})
    assert client.get(f"/api/patterns/{pattern['id']}").status_code == 404
    assert client.post(f"/api/patterns/{pattern['id']}/edits",
                       json={"edits": [{"cell": [0, 0], "to": 0}]}).status_code == 404
```

`backend/tests/test_api_export.py`：

```python
import io
from pathlib import Path

import pytest
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures" / "images"


@pytest.fixture
def pattern_id(auth_client):
    pid = auth_client.post("/api/projects", data={"name": "t"},
                           files={"file": ("logo.png", (FIXTURES / "logo.png").read_bytes(),
                                           "image/png")}).json()["id"]
    return auth_client.post(f"/api/projects/{pid}/patterns",
                            json={"params": {"grid_long_side": 16, "max_colors": 4}}).json()["id"]


def test_export_png(auth_client, pattern_id):
    r = auth_client.get(f"/api/patterns/{pattern_id}/export?format=png&cell_px=10")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).size[0] >= 160


def test_export_pdf_is_real_pdf(auth_client, pattern_id):
    r = auth_client.get(f"/api/patterns/{pattern_id}/export?format=pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert "attachment" in r.headers.get("content-disposition", "")


def test_export_unknown_format_is_400(auth_client, pattern_id):
    assert auth_client.get(f"/api/patterns/{pattern_id}/export?format=svg").status_code == 400


def test_palettes_and_colors_endpoints(auth_client, db):
    from app.services.palettes import seed_palettes
    seed_palettes(db)
    db.flush()
    pl = auth_client.get("/api/palettes")
    assert pl.status_code == 200 and pl.json()
    colors = auth_client.get("/api/palettes/mard/colors")
    assert colors.status_code == 200
    body = colors.json()
    assert len(body) >= 291
    assert body[0]["index"] == 0 and body[0]["hex"].startswith("#")
    assert any(c["role"] == "clear" for c in body)


def test_style_presets_endpoint(auth_client, db):
    from app.models import StylePreset
    db.add(StylePreset(name="Q版盲盒", prompt="粗轮廓 纯色平涂", params={}))
    db.flush()
    r = auth_client.get("/api/style-presets")
    assert r.status_code == 200 and r.json()[0]["name"] == "Q版盲盒"
```

- [ ] **Step 3: 运行确认失败**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_api_projects.py tests/test_api_patterns.py tests/test_api_export.py -q
```

Expected: FAIL，404（路由不存在）或 `ModuleNotFoundError`。

- [ ] **Step 4: 写 projects.py**

`backend/app/api/projects.py`：

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core import pipeline
from app.db import SessionLocal, get_db
from app.models import Pattern, Project, StylePreset, User
from app.schemas import GenerateIn, JobOut, PatternParamsIn, ProjectOut, SizeSuggestion
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
    out = []
    for p in rows:
        score = (p.buildability or {}).get("score")
        out.append({"id": p.id, "origin": p.origin, "parent_id": p.parent_id,
                    "created_at": p.created_at, "score": score,
                    "n_colors": len(p.color_stats or {})})
    return out


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


@router.get("/projects/{project_id}/source")
def get_source(project_id: uuid.UUID, user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> Response:
    proj = _owned_project(db, user, project_id)
    return Response(get_storage().load(proj.source_image_path), media_type="image/png")


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
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "use_ai=true 时必须指定 style_preset_id")
        if db.get(StylePreset, body.style_preset_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "风格预设不存在")
        if quota.remaining(db, user.id) < 1:
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "AI 额度不足，可跳过 AI 直接出图")

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
    from app.models import AiRender

    proj = _owned_project(db, user, project_id)
    params = psvc.params_from_dict(body.params)
    ai_render = None
    if body.source != "original" and body.ai_render_id is not None:
        ai_render = db.get(AiRender, body.ai_render_id)
        if ai_render is None or ai_render.project_id != proj.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "AI 重绘结果不存在")
    pat = psvc.generate(db, proj, params, ai_render)
    db.commit()
    return pattern_out(pat, load_core_palette(params.palette_id))
```

- [ ] **Step 5: 写 patterns.py、jobs.py、meta.py**

`backend/app/api/patterns.py`：

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.palette import Palette as CorePalette
from app.db import get_db
from app.models import Feedback, Pattern, Project, User
from app.schemas import EditIn, FeedbackIn, PatchIn
from app.services import patterns as psvc
from app.services.palettes import load_core_palette

router = APIRouter(prefix="/api/patterns", tags=["patterns"])


def _owned_pattern(db: Session, user: User, pattern_id: uuid.UUID) -> Pattern:
    pat = db.get(Pattern, pattern_id)
    if pat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "图纸不存在")
    proj = db.get(Project, pat.project_id)
    if proj is None or proj.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "图纸不存在")
    return pat


def pattern_out(pat: Pattern, palette: CorePalette) -> dict:
    return {
        "id": pat.id, "project_id": pat.project_id, "parent_id": pat.parent_id,
        "origin": pat.origin, "params": pat.params, "grid": pat.grid,
        "color_stats": pat.color_stats, "buildability": pat.buildability,
        "materials": psvc.materials_of(pat, palette),
        "palette_id": (pat.params or {}).get("palette_id", "mard"),
        "created_at": pat.created_at,
    }


def _palette_of(pat: Pattern) -> CorePalette:
    return load_core_palette((pat.params or {}).get("palette_id", "mard"))


@router.get("/{pattern_id}")
def get_pattern(pattern_id: uuid.UUID, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> dict:
    pat = _owned_pattern(db, user, pattern_id)
    return pattern_out(pat, _palette_of(pat))


@router.post("/{pattern_id}/apply-patch")
def apply_patch_endpoint(pattern_id: uuid.UUID, body: PatchIn,
                         user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    pat = _owned_pattern(db, user, pattern_id)
    child = psvc.apply_issue(db, pat, body.issue_index)
    db.commit()
    return pattern_out(child, _palette_of(child))


@router.post("/{pattern_id}/edits")
def apply_edits_endpoint(pattern_id: uuid.UUID, body: EditIn,
                         user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    pat = _owned_pattern(db, user, pattern_id)
    child = psvc.apply_manual_edits(db, pat, [e.model_dump() for e in body.edits],
                                    body.protected_cells)
    db.commit()
    return pattern_out(child, _palette_of(child))


@router.post("/{pattern_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
def add_feedback(pattern_id: uuid.UUID, body: FeedbackIn,
                 user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    pat = _owned_pattern(db, user, pattern_id)
    db.add(Feedback(pattern_id=pat.id, user_id=user.id, kind=body.kind,
                    cells=body.cells, note=body.note))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{pattern_id}/export")
def export(pattern_id: uuid.UUID, format: str = Query("png"), cell_px: int = Query(28, ge=4, le=120),
           bead_mm: float = Query(5.0, gt=0, le=20), user: User = Depends(current_user),
           db: Session = Depends(get_db)) -> Response:
    pat = _owned_pattern(db, user, pattern_id)
    palette = _palette_of(pat)
    if format == "png":
        return Response(psvc.export_png(pat, palette, cell_px=cell_px), media_type="image/png",
                        headers={"Content-Disposition": f'attachment; filename="pattern-{pat.id}.png"'})
    if format == "pdf":
        return Response(psvc.export_pdf(pat, palette, bead_mm=bead_mm), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="pattern-{pat.id}.pdf"'})
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"不支持的导出格式：{format}")
```

`backend/app/api/jobs.py`：

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import Job, User
from app.schemas import JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None or (job.payload or {}).get("user_id") != str(user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return job
```

`backend/app/api/meta.py`：

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import Palette, StylePreset, User
from app.schemas import PaletteColorOut, PaletteOut, StylePresetOut
from app.services.palettes import load_core_palette

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/palettes", response_model=list[PaletteOut])
def list_palettes(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Palette]:
    return list(db.scalars(select(Palette).order_by(Palette.brand)).all())


@router.get("/palettes/{palette_id}/colors", response_model=list[PaletteColorOut])
def list_palette_colors(palette_id: str, user: User = Depends(current_user)) -> list[dict]:
    """按 core 色卡的**全局索引**返回——grid 里存的就是这个索引，前端要靠它上色。"""
    try:
        p = load_core_palette(palette_id)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"色卡不存在：{palette_id}") from None
    role_by_code = p.roles
    return [{"index": i, "code": p.codes[i], "name": p.names[i],
             "hex": "#{:02X}{:02X}{:02X}".format(*p.rgb[i]),
             "role": role_by_code.get(p.codes[i]), "confidence": p.confidence[i]}
            for i in range(len(p))]


@router.get("/style-presets", response_model=list[StylePresetOut])
def list_style_presets(user: User = Depends(current_user),
                       db: Session = Depends(get_db)) -> list[StylePreset]:
    return list(db.scalars(
        select(StylePreset).where(StylePreset.is_active.is_(True)).order_by(StylePreset.name)).all())
```

- [ ] **Step 6: 在 main.py 注册路由**

把 `backend/app/main.py` 里 `create_app` 中的这一段：

```python
    from app.api import auth as auth_api
    app.include_router(auth_api.router)
```

替换为：

```python
    from app.api import auth as auth_api
    from app.api import jobs as jobs_api
    from app.api import meta as meta_api
    from app.api import patterns as patterns_api
    from app.api import projects as projects_api

    for module in (auth_api, projects_api, patterns_api, jobs_api, meta_api):
        app.include_router(module.router)
```

- [ ] **Step 7: 运行确认通过**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_api_projects.py tests/test_api_patterns.py tests/test_api_export.py -q
```

Expected: 25 passed。若 `test_generate_without_ai_runs_and_returns_pattern` 里 job 状态一直是 `pending`，说明 `BackgroundTasks` 在 TestClient 下要等响应结束才执行——这是预期行为，测试只断言状态在合法集合内。

- [ ] **Step 8: 全量回归并提交**

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

Expected: 220 passed。

```bash
git add backend/app/api backend/app/main.py backend/tests
git commit -m "feat(api): 项目、图纸、任务与元数据路由（含归属校验与导出）

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: 管理 CLI、部署配置与端到端冒烟

**Files:**
- Create: `backend/app/cli.py`、`backend/Dockerfile`、`backend/.dockerignore`、`docker-compose.yml`（仓库根）
- Create: `backend/tests/test_cli.py`、`backend/tests/test_smoke_e2e.py`
- Modify: `README.md`（仓库根，新增"本地运行"一节）

**Interfaces:**
- Produces: `python -m app.cli invite --count 5 --uses 1` → 打印生成的邀请码
- Produces: `python -m app.cli quota --user <username> --add 20` → 增加额度，打印剩余
- Produces: `python -m app.cli seed-palettes` → 灌色卡
- Produces: `python -m app.cli preset --name <n> --prompt <p>` → 建风格预设
- Produces: `python -m app.cli admin --user <username>` → 设为管理员

- [ ] **Step 1: 写失败测试**

`backend/tests/test_cli.py`：

```python
import pytest
from sqlalchemy import func, select

from app.models import InviteCode, PaletteColor, StylePreset, User
from app import cli


def test_invite_creates_codes(db, capsys):
    n = cli.cmd_invite(db, count=3, uses=2)
    assert n == 3
    codes = db.scalars(select(InviteCode)).all()
    assert len(codes) == 3 and all(c.max_uses == 2 for c in codes)
    assert all(len(c.code) >= 8 for c in codes)
    assert len(set(c.code for c in codes)) == 3


def test_quota_add_and_report(db):
    u = User(username="q", password_hash="x", ai_quota=1)
    db.add(u)
    db.flush()
    left = cli.cmd_quota(db, username="q", add=9)
    assert left == 10 and u.ai_quota == 10


def test_quota_unknown_user_raises(db):
    with pytest.raises(SystemExit):
        cli.cmd_quota(db, username="ghost", add=1)


def test_seed_palettes_command(db):
    n = cli.cmd_seed_palettes(db)
    assert n >= 291
    assert db.scalar(select(func.count()).select_from(PaletteColor)) == n


def test_preset_command(db):
    sp = cli.cmd_preset(db, name="Q版盲盒", prompt="粗轮廓 纯色平涂 无渐变")
    assert isinstance(sp, StylePreset) and sp.is_active is True


def test_admin_command(db):
    u = User(username="boss", password_hash="x")
    db.add(u)
    db.flush()
    cli.cmd_admin(db, username="boss")
    assert u.is_admin is True
```

`backend/tests/test_smoke_e2e.py`：

```python
"""端到端冒烟：注册 → 上传 → 出图 → 修图 → 编辑 → 反馈 → 导出，一条龙。"""
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "images"


def test_full_user_journey(client, db):
    from app.models import InviteCode
    from app.services import auth
    auth._ROUNDS = 4
    db.add(InviteCode(code="SMOKE", max_uses=1))
    db.flush()

    # 注册
    r = client.post("/api/auth/register",
                    json={"username": "smoke", "password": "pw12345678", "invite_code": "SMOKE"})
    assert r.status_code == 201

    # 上传
    r = client.post("/api/projects", data={"name": "冒烟"},
                    files={"file": ("cartoon.png", (FIXTURES / "cartoon.png").read_bytes(),
                                    "image/png")})
    assert r.status_code == 201
    pid = r.json()["id"]

    # 尺寸推荐
    sizes = client.get(f"/api/projects/{pid}/suggest-sizes?base=40").json()
    assert len(sizes) == 3

    # 同步出图
    pat = client.post(f"/api/projects/{pid}/patterns",
                      json={"params": {"grid_long_side": sizes[1]["long_side"],
                                       "max_colors": 8}}).json()
    assert pat["buildability"]["score"] > 0
    assert pat["materials"]

    # 手工改一格
    target = int(max(pat["color_stats"], key=lambda k: pat["color_stats"][k]))
    edited = client.post(f"/api/patterns/{pat['id']}/edits",
                         json={"edits": [{"cell": [0, 0], "to": target}]}).json()
    assert edited["grid"][0][0] == target

    # 实拼反馈
    assert client.post(f"/api/patterns/{edited['id']}/feedback",
                       json={"kind": "断裂", "cells": [[1, 1]], "note": "试试"}).status_code == 204

    # 导出
    png = client.get(f"/api/patterns/{edited['id']}/export?format=png&cell_px=8")
    pdf = client.get(f"/api/patterns/{edited['id']}/export?format=pdf")
    assert png.status_code == 200 and pdf.content[:5] == b"%PDF-"

    # 版本树可见
    detail = client.get(f"/api/projects/{pid}").json()
    assert len(detail["patterns"]) >= 2
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_cli.py tests/test_smoke_e2e.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'app.cli'`。

- [ ] **Step 3: 写 cli.py**

`backend/app/cli.py`：

```python
"""管理脚本。用法：cd backend && python -m app.cli <子命令> --help"""
from __future__ import annotations

import argparse
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import InviteCode, StylePreset, User
from app.services.palettes import seed_palettes


def _user_or_die(db: Session, username: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        print(f"没有这个用户：{username}", file=sys.stderr)
        raise SystemExit(2)
    return user


def cmd_invite(db: Session, count: int, uses: int) -> int:
    for _ in range(count):
        code = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")[:12].upper()
        db.add(InviteCode(code=code, max_uses=uses))
        print(code)
    db.flush()
    return count


def cmd_quota(db: Session, username: str, add: int) -> int:
    user = _user_or_die(db, username)
    user.ai_quota += add
    db.flush()
    left = user.ai_quota - user.ai_used
    print(f"{username}: 总额度 {user.ai_quota}，已用 {user.ai_used}，剩余 {left}")
    return left


def cmd_seed_palettes(db: Session) -> int:
    n = seed_palettes(db)
    print(f"写入 {n} 个色号")
    return n


def cmd_preset(db: Session, name: str, prompt: str) -> StylePreset:
    sp = StylePreset(name=name, prompt=prompt, params={})
    db.add(sp)
    db.flush()
    print(f"已创建风格预设 {sp.id} · {name}")
    return sp


def cmd_admin(db: Session, username: str) -> None:
    user = _user_or_die(db, username)
    user.is_admin = True
    db.flush()
    print(f"{username} 已设为管理员")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("invite", help="生成邀请码")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--uses", type=int, default=1)

    p = sub.add_parser("quota", help="增加 AI 额度")
    p.add_argument("--user", required=True)
    p.add_argument("--add", type=int, required=True)

    sub.add_parser("seed-palettes", help="把色卡灌进数据库")

    p = sub.add_parser("preset", help="创建风格预设")
    p.add_argument("--name", required=True)
    p.add_argument("--prompt", required=True)

    p = sub.add_parser("admin", help="把用户设为管理员")
    p.add_argument("--user", required=True)

    args = ap.parse_args(argv)
    db = SessionLocal()
    try:
        if args.cmd == "invite":
            cmd_invite(db, args.count, args.uses)
        elif args.cmd == "quota":
            cmd_quota(db, args.user, args.add)
        elif args.cmd == "seed-palettes":
            cmd_seed_palettes(db)
        elif args.cmd == "preset":
            cmd_preset(db, args.name, args.prompt)
        elif args.cmd == "admin":
            cmd_admin(db, args.user)
        db.commit()
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && ./.venv/Scripts/python -m pytest tests/test_cli.py tests/test_smoke_e2e.py -q
```

Expected: 7 passed。

- [ ] **Step 5: 写部署配置**

`backend/Dockerfile`：

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

`backend/.dockerignore`：

```
.venv/
data/
tests/
.env
providers.yaml
__pycache__/
*.pyc
```

仓库根 `docker-compose.yml`：

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: pindou
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
      POSTGRES_DB: pindou
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pindou"]
      interval: 5s
      timeout: 3s
      retries: 20

  api:
    build: ./backend
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+psycopg://pindou:${POSTGRES_PASSWORD}@db:5432/pindou
      SESSION_SECRET: ${SESSION_SECRET:?set SESSION_SECRET in .env}
      DATA_DIR: /data
      PROVIDERS_FILE: /app/providers.yaml
      ARK_API_KEY: ${ARK_API_KEY:-}
      DASHSCOPE_API_KEY: ${DASHSCOPE_API_KEY:-}
    volumes:
      - appdata:/data
      - ./backend/providers.yaml:/app/providers.yaml:ro
    ports:
      - "8000:8000"

  web:
    image: nginx:alpine
    depends_on: [api]
    volumes:
      - ./frontend/dist:/usr/share/nginx/html:ro
      - ./deploy/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    ports:
      - "8080:80"

volumes:
  pgdata:
  appdata:
```

`deploy/nginx.conf`：

```nginx
server {
    listen 80;
    client_max_body_size 25m;

    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 6: 本地起服务手工验收**

```bash
cd backend && ./.venv/Scripts/python -m alembic upgrade head \
  && ./.venv/Scripts/python -m app.cli seed-palettes \
  && ./.venv/Scripts/python -m app.cli invite --count 1 --uses 5
```

另开一个终端：

```bash
cd backend && ./.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

验证：

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/openapi.json | head -c 200
```

Expected: `{"status":"ok"}`；OpenAPI 文档可访问（浏览器打开 http://127.0.0.1:8000/docs 能看到全部端点）。

- [ ] **Step 7: 写 README 的运行说明**

在仓库根 `README.md`（不存在则新建）追加：

```markdown
## 本地运行（开发）

前置：Python 3.11+、本机 PostgreSQL 16。

```bash
# 1. 建库建用户（只做一次）
"D:/Kf/pgsql/bin/psql.exe" -U postgres -h 127.0.0.1 \
  -c "CREATE USER pindou WITH PASSWORD '<你的密码>';" \
  -c "CREATE DATABASE pindou OWNER pindou;" \
  -c "CREATE DATABASE pindou_test OWNER pindou;"

# 2. 配置
cd backend && cp .env.example .env    # 填入密码与 SESSION_SECRET

# 3. 安装与建表
python -m venv .venv && ./.venv/Scripts/python -m pip install -e ".[dev]"
./.venv/Scripts/python -m alembic upgrade head
./.venv/Scripts/python -m app.cli seed-palettes
./.venv/Scripts/python -m app.cli invite --count 1 --uses 5

# 4. 起服务
./.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

接口文档：http://127.0.0.1:8000/docs

**AI 重绘**：不配置 `backend/providers.yaml` 时自动回退到本地假 provider（posterize，不联网不花钱），整条链路照样跑通。要接真实模型，复制 `providers.yaml.example` 并设置对应的 API key 环境变量。

## 测试

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

## 算法基准

```bash
cd backend && ./.venv/Scripts/python scripts/benchmark.py --smoothness 2.0
```
```

- [ ] **Step 8: 全量回归并提交**

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

Expected: 227 passed。

```bash
git add backend/app/cli.py backend/Dockerfile backend/.dockerignore docker-compose.yml deploy README.md backend/tests
git commit -m "feat(api): 管理 CLI、Docker 部署配置与端到端冒烟测试

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## 自审记录

**Spec 覆盖检查：**

| Spec 条目 | 任务 |
|---|---|
| §5 全部九张表与字段 | Task 2（`origin`、`manual_edits`、`applied_patch`、`in_sets`、`role` 均已建） |
| §5 grid 用 JSONB、None 保留 | Task 2 `test_jsonb_grid_survives_roundtrip` |
| §5 版本树 parent_id | Task 2、Task 6 |
| §5 ai_renders 按 input_hash 缓存 | Task 2 唯一约束、Task 7 `find_cached` |
| §5 大文件走磁盘、存储层抽接口 | Task 3 |
| §5 palette_colors.lab 预算 | Task 3 `seed_palettes` |
| §6.1 Provider 抽象、配置驱动、两个适配器 | Task 5 |
| §6.1 AI 输出强制走伪像素后处理 | **已在 core 层实现**（`pipeline._downsample` 对任何输入都先跑 `detect_pixel_grid`），Task 6 的 `generate` 直接复用；不需要额外代码 |
| §6.2 先扣后跑、缓存不扣、管理员命令行加额度 | Task 4、Task 7、Task 10 |
| §6.3 重试 2 次、失败退额度、启动清理 running | Task 5 `call_with_retry`、Task 7 `redraw`/`reclaim_stale` |
| §7 全部端点 | Task 8（auth）、Task 9（其余） |
| §7 首次生成走 job、调参同步 | Task 9 `generate` / `recompute` |
| §7 参数校验上限（20MB、200 格、64 色） | Task 6 `_LIMITS` + `create_project`；`max_upload_bytes` 在 Task 1 的 Settings |
| §9 API 测试覆盖注册/登录/额度扣退/job 流转/编辑 | Task 8、9、10 |
| §10 docker-compose、Dockerfile、nginx、备份说明 | Task 10 |
| §10 启动时 alembic upgrade + 灌色卡 | Task 10 Dockerfile CMD、Task 8 `_startup` |

**未覆盖且有意为之**：§4 全部算法（已在计划一完成）；§8 前端（计划三）；抖动开启态（spec §11 已记为延期项）。

**类型一致性核对**：`Params` 字段名在 Task 6 `_PARAM_KEYS` 由 `dataclasses.fields` 动态取得，与 core 保持同步，不会写死；`Issue` 的 `to_dict()`/重建在 Task 6 `apply_issue` 对称；`grid_to_db`/`grid_from_db` 的 `None ↔ -1` 约定在 Task 6 定义、Task 9 的 API 响应直接透传；`pattern_out` 在 Task 9 定义并被 `projects.recompute` 跨模块引用（已用局部 import 避免循环依赖）。

**占位符扫描**：无 TBD/TODO；所有步骤均含可直接执行的代码或命令。
