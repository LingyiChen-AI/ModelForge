import httpx
import pytest
from modelforge_common.llm_client import chat, ChatResult, LLMError


def _patch(monkeypatch, handler):
    monkeypatch.setattr(
        "modelforge_common.llm_client._client",
        lambda timeout: httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_chat_success(monkeypatch):
    def handler(request):
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["authorization"] == "Bearer sk-test"
        import json
        body = json.loads(request.content)
        assert body == {"model": "gpt-x", "messages": [{"role": "user", "content": "1+1=?"}]}
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "2"}}],
            "usage": {"total_tokens": 3},
        })
    _patch(monkeypatch, handler)
    res = chat("https://api.x.com/v1", "sk-test", "gpt-x",
               [{"role": "user", "content": "1+1=?"}])
    assert isinstance(res, ChatResult)
    assert res.content == "2"
    assert res.usage == {"total_tokens": 3}


def test_chat_http_error(monkeypatch):
    _patch(monkeypatch, lambda r: httpx.Response(401, text="unauthorized"))
    with pytest.raises(LLMError) as ei:
        chat("https://api.x.com/v1", "bad", "gpt-x", [{"role": "user", "content": "x"}])
    assert ei.value.status == 401


def test_chat_malformed_body(monkeypatch):
    _patch(monkeypatch, lambda r: httpx.Response(200, json={"oops": True}))
    with pytest.raises(LLMError) as ei:
        chat("https://api.x.com/v1", "sk", "gpt-x", [{"role": "user", "content": "x"}])
    assert ei.value.status == 200


def test_chat_network_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("boom")
    _patch(monkeypatch, handler)
    with pytest.raises(LLMError) as ei:
        chat("https://api.x.com/v1", "sk", "gpt-x", [{"role": "user", "content": "x"}])
    assert ei.value.status is None


def test_chat_none_content(monkeypatch):
    _patch(monkeypatch, lambda r: httpx.Response(200, json={
        "choices": [{"message": {"content": None}}]}))
    with pytest.raises(LLMError):
        chat("https://api.x.com/v1", "sk", "gpt-x", [{"role": "user", "content": "x"}])


def test_chat_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setattr("modelforge_common.llm_client.time.sleep", lambda *_: None)
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise httpx.ReadTimeout("read timed out")   # 瞬时超时
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    _patch(monkeypatch, handler)
    res = chat("https://api.x.com/v1", "sk", "gpt-x", [{"role": "user", "content": "x"}], retries=2)
    assert res.content == "ok" and calls["n"] == 3   # 失败 2 次后第 3 次成功


def test_chat_no_retry_on_4xx(monkeypatch):
    monkeypatch.setattr("modelforge_common.llm_client.time.sleep", lambda *_: None)
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, text="bad request")
    _patch(monkeypatch, handler)
    with pytest.raises(LLMError):
        chat("https://api.x.com/v1", "sk", "gpt-x", [{"role": "user", "content": "x"}], retries=3)
    assert calls["n"] == 1   # 4xx 客户端错误不重试


def test_chat_retries_exhausted_raises(monkeypatch):
    monkeypatch.setattr("modelforge_common.llm_client.time.sleep", lambda *_: None)
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        raise httpx.ReadTimeout("still timing out")
    _patch(monkeypatch, handler)
    with pytest.raises(LLMError) as ei:
        chat("https://api.x.com/v1", "sk", "gpt-x", [{"role": "user", "content": "x"}], retries=2)
    assert ei.value.status is None and calls["n"] == 3   # 1 次 + 重试 2 次


def test_chat_strips_trailing_slash(monkeypatch):
    seen = {}
    def handler(request):
        seen["path"] = request.url.path
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    _patch(monkeypatch, handler)
    chat("https://api.x.com/v1/", "sk", "gpt-x", [{"role": "user", "content": "x"}])
    assert seen["path"] == "/v1/chat/completions"
