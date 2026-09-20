import base64
import io
from decimal import Decimal

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


def test_build_provider_unknown_adapter_raises(monkeypatch):
    monkeypatch.setenv("SOME_KEY", "x")
    cfg = pbase.ProviderConfig(name="x", adapter="telepathy", base_url="",
                               api_key_env="SOME_KEY", model="")
    with pytest.raises(pbase.ProviderError):
        pbase.build_provider(cfg)


def test_build_provider_missing_key_raises_non_retryable(monkeypatch):
    monkeypatch.delenv("NO_SUCH_KEY", raising=False)
    cfg = pbase.ProviderConfig(name="ark", adapter="openai_compatible",
                               base_url="https://x", api_key_env="NO_SUCH_KEY", model="m")
    with pytest.raises(pbase.ProviderError) as e:
        pbase.build_provider(cfg)
    assert e.value.retryable is False


def test_get_provider_falls_back_to_fake_when_unconfigured(monkeypatch):
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
        return_value=httpx.Response(200, content=_png((1, 2, 3)),
                                    headers={"content-type": "image/png"}))
    assert pbase.build_provider(cfg).redraw(_png(), "p", {}).mime == "image/png"


@respx.mock
@pytest.mark.parametrize("status,retryable",
                         [(429, True), (500, True), (503, True), (400, False), (401, False)])
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
                               extra={"function": "stylization_all", "poll_interval": 0,
                                      "poll_timeout": 10})
    submit = respx.post(
        "https://ds.test/api/v1/services/aigc/image2image/image-synthesis").mock(
        return_value=httpx.Response(200, json={"output": {"task_id": "T1",
                                                          "task_status": "PENDING"}}))
    poll = respx.get("https://ds.test/api/v1/tasks/T1").mock(side_effect=[
        httpx.Response(200, json={"output": {"task_status": "RUNNING"}}),
        httpx.Response(200, json={"output": {"task_status": "SUCCEEDED",
                                             "results": [{"url": "https://cdn.test/r.png"}]}}),
    ])
    respx.get("https://cdn.test/r.png").mock(
        return_value=httpx.Response(200, content=_png(), headers={"content-type": "image/png"}))
    r = pbase.build_provider(cfg).redraw(_png(), "像素风格插画", {})
    assert r.mime == "image/png" and poll.call_count == 2
    assert submit.calls[0].request.headers["x-dashscope-async"] == "enable"


@respx.mock
def test_dashscope_failed_task_raises(monkeypatch):
    monkeypatch.setenv("DS_KEY", "sk-ds")
    cfg = pbase.ProviderConfig(name="ds", adapter="dashscope_native",
                               base_url="https://ds.test/api/v1", api_key_env="DS_KEY",
                               model="m", extra={"poll_interval": 0, "poll_timeout": 10})
    respx.post("https://ds.test/api/v1/services/aigc/image2image/image-synthesis").mock(
        return_value=httpx.Response(200, json={"output": {"task_id": "T2"}}))
    respx.get("https://ds.test/api/v1/tasks/T2").mock(
        return_value=httpx.Response(200, json={"output": {"task_status": "FAILED",
                                                          "message": "nsfw"}}))
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
