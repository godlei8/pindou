from __future__ import annotations

import base64
from decimal import Decimal

import httpx

from app.providers.base import ProviderConfig, ProviderError, RedrawResult
from app.providers.http import shared_client

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
        client = shared_client()
        try:
            resp = client.post(url, json=body, timeout=timeout,
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
                got = client.get(data["url"], timeout=timeout)
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
