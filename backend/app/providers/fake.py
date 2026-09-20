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
        out = img.quantize(colors=8, method=Image.MEDIANCUT,
                           dither=Image.Dither.NONE).convert("RGB")
        buf = io.BytesIO()
        out.save(buf, format="PNG")
        return RedrawResult(image=buf.getvalue(), mime="image/png", model="fake",
                            cost=Decimal("0"), raw={"prompt": prompt})

    def estimate_cost(self, params: dict) -> Decimal:
        return Decimal("0")
