from __future__ import annotations

import os
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


def _export_env_file() -> None:
    """把 .env 里的键灌进 os.environ（已存在的不覆盖）。

    pydantic-settings 只把 .env 读进 Settings 对象，不进 os.environ。
    而 provider 的 API key 是按 `api_key_env` 指定的变量名从 os.environ 取的
    （这样 Docker 里直接传环境变量即可），本地开发就读不到 .env 里的 key 了。
    """
    env_file = _BACKEND_ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


@lru_cache
def get_settings() -> Settings:
    _export_env_file()
    return Settings()
