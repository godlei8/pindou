from __future__ import annotations

from functools import lru_cache

import httpx


@lru_cache
def shared_client() -> httpx.Client:
    """进程内共享的 HTTP 客户端。

    实测 Windows 上 `httpx.Client()` 每次构造要约 1.25 秒（代理探测 + 证书加载），
    每次 AI 调用都新建就是白扔一秒，还会重复 TLS 握手。httpx.Client 本身线程安全，
    超时按请求传 `timeout=` 即可覆盖默认值。
    """
    return httpx.Client(timeout=120, follow_redirects=True)
