from __future__ import annotations

import base64
import io
import time
from decimal import Decimal

import httpx
from PIL import Image

from app.providers.base import ProviderConfig, ProviderError, RedrawResult
from app.providers.http import shared_client

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

# 实测约束：百炼要求输入图每边在 512–4096 像素之间，否则任务直接 FAILED，
# code=InvalidParameter，message="The height of the image should be between 512 and 4096 pixels."
_MIN_SIDE = 512
_MAX_SIDE = 4096


def _fit_input_size(image: bytes) -> bytes:
    """把图缩放到百炼接受的尺寸区间，保持长宽比。已经合规的原样返回。"""
    img = Image.open(io.BytesIO(image))
    w, h = img.size
    scale = 1.0
    if min(w, h) < _MIN_SIDE:
        scale = _MIN_SIDE / min(w, h)
    if max(w, h) * scale > _MAX_SIDE:
        scale = _MAX_SIDE / max(w, h)
    if abs(scale - 1.0) < 1e-9:
        return image

    new_size = (max(_MIN_SIDE, round(w * scale)), max(_MIN_SIDE, round(h * scale)))
    resample = Image.LANCZOS if scale < 1 else Image.NEAREST   # 放大用最近邻，别把硬边糊掉
    out = io.BytesIO()
    img.convert("RGB").resize(new_size, resample).save(out, format="PNG")
    return out.getvalue()


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
        payload_image = _fit_input_size(image)
        body = {
            "model": self.cfg.model,
            "input": {
                "prompt": prompt,
                "function": merged.get("function", "stylization_all"),
                "base_image_url":
                    f"data:image/png;base64,{base64.b64encode(payload_image).decode()}",
            },
            "parameters": {k: merged[k] for k in ("strength", "n", "seed") if k in merged},
        }

        client = shared_client()
        try:
            resp = client.post(submit_url, json=body, timeout=60,
                               headers=self._headers(async_=True))
            if resp.status_code >= 400:
                raise ProviderError(
                    f"{self.name} 提交失败 HTTP {resp.status_code}: {resp.text[:300]}",
                    retryable=resp.status_code in _RETRYABLE_STATUS)
            task_id = (resp.json().get("output") or {}).get("task_id")
            if not task_id:
                raise ProviderError(f"{self.name} 未返回 task_id: {resp.text[:300]}",
                                    retryable=False)

            deadline = time.monotonic() + poll_timeout
            url = None
            while True:
                got = client.get(f"{base}/tasks/{task_id}", headers=self._headers(), timeout=60)
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
                    raise ProviderError(f"{self.name} 轮询超时（{poll_timeout}s）",
                                        retryable=True)
                if poll_interval:
                    time.sleep(poll_interval)

            img_resp = client.get(url, timeout=60)
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
