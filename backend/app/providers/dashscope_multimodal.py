from __future__ import annotations

import base64
from decimal import Decimal

import httpx

from app.providers.base import ProviderConfig, ProviderError, RedrawResult
from app.providers.dashscope_native import _RETRYABLE_STATUS, _fit_input_size
from app.providers.http import shared_client

# 风格预设里存的是「画成什么样」的描述，千问图像编辑要的是一条编辑指令，套一层模板。
_DEFAULT_TEMPLATE = "把这张图重绘成下面的风格，保持主体、构图和姿态不变：{prompt}"


class DashScopeMultimodalProvider:
    """千问图像编辑（qwen-image-2.0 / qwen-image-edit-*）：multimodal-generation 同步接口。

    和万相的异步任务不同，一次 POST 直接返回结果图 URL；失败不计费。
    """

    def __init__(self, cfg: ProviderConfig, api_key: str) -> None:
        self.name = cfg.name
        self.cfg = cfg
        self._key = api_key

    def redraw(self, image: bytes, prompt: str, params: dict) -> RedrawResult:
        merged = {**self.cfg.extra, **params}
        template = merged.get("prompt_template", _DEFAULT_TEMPLATE)
        url = f"{self.cfg.base_url.rstrip('/')}/services/aigc/multimodal-generation/generation"
        payload_image = _fit_input_size(image)
        body = {
            "model": self.cfg.model,
            "input": {"messages": [{"role": "user", "content": [
                {"image": f"data:image/png;base64,{base64.b64encode(payload_image).decode()}"},
                {"text": template.format(prompt=prompt)},
            ]}]},
            "parameters": {"n": 1, "watermark": False,
                           **{k: merged[k] for k in ("negative_prompt", "prompt_extend",
                                                     "size", "seed") if k in merged}},
        }

        client = shared_client()
        try:
            resp = client.post(url, json=body, timeout=float(merged.get("timeout", 180)),
                               headers={"Authorization": f"Bearer {self._key}",
                                        "Content-Type": "application/json"})
            if resp.status_code >= 400:
                raise ProviderError(
                    f"{self.name} 调用失败 HTTP {resp.status_code}: {resp.text[:300]}",
                    retryable=resp.status_code in _RETRYABLE_STATUS)
            data = resp.json()
            choices = (data.get("output") or {}).get("choices") or []
            content = (choices[0].get("message") or {}).get("content") or [] if choices else []
            img_url = next((c["image"] for c in content if c.get("image")), None)
            if not img_url:
                raise ProviderError(
                    f"{self.name} 未返回结果图: {data.get('code', '')} {data.get('message', '')}",
                    retryable=False)

            img_resp = client.get(img_url, timeout=60)
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
