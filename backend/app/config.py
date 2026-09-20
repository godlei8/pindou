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
