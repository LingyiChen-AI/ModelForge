"""OpenAI 协议(/chat/completions)的最小 httpx 封装。
app-server 用于设置页连通性测试,train-worker 在 Prompt 评测阶段复用。
"""
from __future__ import annotations

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


def chat(base_url: str, api_key: str, model_id: str,
         messages: list[dict], *, timeout: float = 30.0) -> ChatResult:
    """POST {base_url}/chat/completions。成功返回 ChatResult;
    超时 / 4xx / 5xx / 网络错 / 响应缺字段 统一抛 LLMError。"""
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
