"""OpenAI 协议(/chat/completions)的最小 httpx 封装。
app-server 用于设置页连通性测试,ml-worker 在 Prompt 评测阶段复用。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

__all__ = ["chat", "ChatResult", "LLMError"]


class LLMError(Exception):
    def __init__(self, status: int | None, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class ChatResult:
    content: str
    usage: dict | None
    raw: dict


def _client(timeout: float) -> httpx.Client:
    # separated into a factory so tests can monkeypatch in an httpx.MockTransport
    return httpx.Client(timeout=timeout)


def _retryable(e: LLMError) -> bool:
    """值得重试的瞬时错误:网络/超时(status=None)、限流(429)、服务端错误(5xx)。
    4xx 客户端错误(鉴权/请求非法)重试也没用,不重试。"""
    return e.status is None or e.status == 429 or (e.status is not None and e.status >= 500)


def _chat_once(base_url: str, api_key: str, model_id: str,
               messages: list[dict], timeout: float) -> ChatResult:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {"model": model_id, "messages": messages}
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        with _client(timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise LLMError(None, f"请求失败: {e}") from e
    if resp.status_code >= 400:
        raise LLMError(resp.status_code, f"HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        raw = resp.json()
        content = raw["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise LLMError(resp.status_code, f"响应解析失败: {e}") from e
    if not isinstance(content, str):
        raise LLMError(resp.status_code, f"响应 content 非字符串: {content!r}")
    return ChatResult(content=content, usage=raw.get("usage"), raw=raw)


def chat(base_url: str, api_key: str, model_id: str,
         messages: list[dict], *, timeout: float = 30.0,
         retries: int = 0, backoff: float = 1.0) -> ChatResult:
    """POST {base_url}/chat/completions。成功返回 ChatResult;
    超时 / 4xx / 5xx / 网络错 / 响应缺字段 统一抛 LLMError。

    retries>0 时对**瞬时错误**(超时/网络/429/5xx)指数退避重试(backoff, 2*backoff, …),
    最多重试 retries 次;客户端错误(4xx)不重试。默认 retries=0 = 不重试(保持连通性测试行为)。
    """
    last: LLMError | None = None
    for attempt in range(retries + 1):
        try:
            return _chat_once(base_url, api_key, model_id, messages, timeout)
        except LLMError as e:
            last = e
            if attempt < retries and _retryable(e):
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
    assert last is not None
    raise last   # pragma: no cover  (循环必然 return 或 raise)
