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


def has_key(cfg: ProviderConfig) -> bool:
    return cfg.adapter == "fake" or bool(os.environ.get(cfg.api_key_env, ""))


def get_provider(name: str | None = None) -> ImageProvider:
    """按名取 provider；不指定名字时，挑第一个**真的配了 key** 的。

    providers.yaml 常常是从样例复制来的、同时列着几家，而用户往往只有其中
    一家的 key。盲选第一条会让整个 AI 功能因为一个无关条目而不可用。
    显式点名的情况不做这种兜底——那是配置错误，应当明确报错。
    """
    from app.providers.fake import FakeProvider

    cfgs = _configs()
    if not cfgs:
        return FakeProvider()

    if name is not None:
        cfg = cfgs.get(name)
        if cfg is None:
            raise ProviderError(f"未配置的 provider: {name!r}", retryable=False)
        return build_provider(cfg)

    usable = next((c for c in cfgs.values() if has_key(c)), None)
    if usable is None:
        return FakeProvider()
    return build_provider(usable)


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
