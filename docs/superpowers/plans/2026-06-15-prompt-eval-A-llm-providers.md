# 子项目 A:LLM 设置页(模型供应商配置)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让有 `llm:manage` 权限的用户在「设置」页配置 OpenAI 协议的大模型供应商(下挂多个 model-id)、一键测试连通性,配置全局共享供后续 Prompt 评测复用。

**Architecture:** app-server 新增 `llm_providers` / `llm_models` 两张表与 `/llm` CRUD + 测试端点;连外部大模型的逻辑抽到 `services/common` 的共享 `llm_client`(OpenAI `/chat/completions`,httpx),app-server 的测试端点同步直调、worker 后续复用;前端新增设置页。api_key 明文存库、读取掩码。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + 编号 SQL 迁移;httpx;pytest;React 19 + Vite + TS + Tailwind v4。

**Spec:** [`docs/superpowers/specs/2026-06-15-prompt-eval-A-llm-providers-design.md`](../specs/2026-06-15-prompt-eval-A-llm-providers-design.md)

**项目铁律(见 `CLAUDE.md`)**:改 `app/models/**` 必须在同一提交里加一个【下一个编号】的 `db/migrations/NNN_*.sql`(幂等);不要用 Alembic。改 RBAC 权限目录时 `app/bootstrap.py` 与编号迁移两处一起改。当前最新迁移 = `016_api_key_plaintext.sql`,本计划新增 `017`、`018`。

## 文件结构

| 文件 | 职责 | 任务 |
|---|---|---|
| `services/common/modelforge_common/llm_client.py` | OpenAI 协议 httpx 封装:`chat()` / `ChatResult` / `LLMError` | T1 |
| `services/common/pyproject.toml` | 加 `httpx` 依赖 | T1 |
| `services/common/tests/test_llm_client.py` | `llm_client` 单测 | T1 |
| `services/app-server/app/models/llm.py` | `LlmProvider` / `LlmModel` 模型 + `mask_key` | T2 |
| `services/app-server/app/models/__init__.py` | 注册新模型 | T2 |
| `services/app-server/db/migrations/017_llm_providers.sql` | 建两张表 | T2 |
| `services/app-server/app/bootstrap.py` | 加 `llm:manage` 权限 | T3 |
| `services/app-server/db/migrations/018_llm_manage_perm.sql` | 写权限种子 | T3 |
| `services/app-server/app/schemas/llm.py` | 请求/响应 schema(掩码) | T4 |
| `services/app-server/app/services/llm_provider_service.py` | provider/model CRUD + 测试 | T5 |
| `services/app-server/app/api/llm.py` | `/llm` 路由 | T6 |
| `services/app-server/app/main.py` | 注册路由 | T6 |
| `services/app-server/tests/test_llm_providers.py` | 模型/service/API 测试 | T2,T5,T6 |
| `frontend/src/api/client.ts` | LLM provider API client | T7 |
| `frontend/src/pages/SettingsPage.tsx` | 设置页 | T8 |
| `frontend/src/App.tsx` | 路由 `/settings` | T8 |
| `frontend/src/components/AppShell.tsx` | 导航「设置」入口 | T8 |

---

### Task 1: 共享 LLM 客户端 `llm_client`

**Files:**
- Create: `services/common/modelforge_common/llm_client.py`
- Modify: `services/common/pyproject.toml`
- Test: `services/common/tests/test_llm_client.py`

- [ ] **Step 1: 加 httpx 依赖**

把 `services/common/pyproject.toml` 顶部 `[project]` 段改为带依赖(其余段不动):

```toml
[project]
name = "modelforge-common"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["httpx>=0.27"]
```

重新安装共享包(后续 import 才有 httpx):

```bash
pip install -e services/common
```

- [ ] **Step 2: 写失败测试**

`services/common/tests/test_llm_client.py`:

```python
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
    with pytest.raises(LLMError):
        chat("https://api.x.com/v1", "sk", "gpt-x", [{"role": "user", "content": "x"}])


def test_chat_network_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("boom")
    _patch(monkeypatch, handler)
    with pytest.raises(LLMError) as ei:
        chat("https://api.x.com/v1", "sk", "gpt-x", [{"role": "user", "content": "x"}])
    assert ei.value.status is None
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd services/common && pytest tests/test_llm_client.py -q`
Expected: FAIL(`ModuleNotFoundError: modelforge_common.llm_client`)

- [ ] **Step 4: 实现 `llm_client`**

`services/common/modelforge_common/llm_client.py`:

```python
"""OpenAI 协议(/chat/completions)的最小 httpx 封装。
app-server 用于设置页连通性测试,train-worker 在 Prompt 评测阶段复用。
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx


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
    return ChatResult(content=content, usage=raw.get("usage"), raw=raw)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd services/common && pytest tests/test_llm_client.py -q`
Expected: PASS(4 passed)

- [ ] **Step 6: 提交**

```bash
git add services/common/modelforge_common/llm_client.py services/common/pyproject.toml services/common/tests/test_llm_client.py
git commit -m "feat(common): add shared OpenAI-protocol llm_client"
```

---

### Task 2: 数据模型 + 迁移 017

**Files:**
- Create: `services/app-server/app/models/llm.py`
- Modify: `services/app-server/app/models/__init__.py`
- Create: `services/app-server/db/migrations/017_llm_providers.sql`
- Test: `services/app-server/tests/test_llm_providers.py`

- [ ] **Step 1: 写失败测试(模型 + 掩码 + 级联)**

`services/app-server/tests/test_llm_providers.py`:

```python
from tests.conftest import make_user, auth_headers


def test_provider_model_and_mask(session_factory):
    from app.models.llm import LlmProvider, LlmModel, mask_key
    assert mask_key("sk-1234567890cdef") == "sk-…cdef"
    assert mask_key("abc") == "…"
    assert mask_key("") == ""
    db = session_factory()
    p = LlmProvider(name="openai", base_url="https://api.openai.com/v1", api_key="sk-secret-abcd")
    p.models.append(LlmModel(model_id="gpt-4o-mini"))
    db.add(p); db.commit(); db.refresh(p)
    assert p.id and p.enabled is True
    assert p.masked_key == "sk-…abcd"
    assert [m.model_id for m in p.models] == ["gpt-4o-mini"]


def test_provider_delete_cascades_models(session_factory):
    from app.models.llm import LlmProvider, LlmModel
    from sqlalchemy import select
    db = session_factory()
    p = LlmProvider(name="x", base_url="u", api_key="k")
    p.models.append(LlmModel(model_id="m1"))
    db.add(p); db.commit()
    db.delete(p); db.commit()
    assert db.execute(select(LlmModel)).first() is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_llm_providers.py -q`
Expected: FAIL(`ModuleNotFoundError: app.models.llm`)

- [ ] **Step 3: 实现模型**

`services/app-server/app/models/llm.py`:

```python
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, CreatorMixin


def mask_key(key: str | None) -> str:
    """脱敏展示 api_key:长度 ≤ 4 → '…';否则前 3 + '…' + 后 4。"""
    if not key:
        return ""
    if len(key) <= 4:
        return "…"
    return key[:3] + "…" + key[-4:]


class LlmProvider(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    base_url: Mapped[str] = mapped_column()
    api_key: Mapped[str] = mapped_column()          # 明文存;响应只出 masked_key
    enabled: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    models: Mapped[list["LlmModel"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", back_populates="provider")

    @property
    def masked_key(self) -> str:
        return mask_key(self.api_key)


class LlmModel(Base, TimestampMixin):
    __tablename__ = "llm_models"
    __table_args__ = (UniqueConstraint("provider_id", "model_id",
                                       name="uq_llm_models_provider_model"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("llm_providers.id", ondelete="CASCADE"))
    model_id: Mapped[str] = mapped_column()
    provider: Mapped["LlmProvider"] = relationship(back_populates="models")
```

- [ ] **Step 4: 注册模型**

把 `services/app-server/app/models/__init__.py` 加上 llm 模型(import 段加一行、`__all__` 加两项):

```python
from app.models.badcase import Badcase
from app.models.llm import LlmProvider, LlmModel
```

并在 `__all__` 列表末尾(`"Badcase",` 之后)加:

```python
    "LlmProvider",
    "LlmModel",
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_llm_providers.py -q`
Expected: PASS(2 passed)

- [ ] **Step 6: 写迁移 017**

`services/app-server/db/migrations/017_llm_providers.sql`:

```sql
CREATE TABLE IF NOT EXISTS llm_providers (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    base_url    TEXT NOT NULL,
    api_key     TEXT NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT true,
    created_by  INTEGER REFERENCES users(id),
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS llm_models (
    id          SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES llm_providers(id) ON DELETE CASCADE,
    model_id    TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now(),
    UNIQUE (provider_id, model_id)
);
CREATE INDEX IF NOT EXISTS ix_llm_models_provider ON llm_models(provider_id);
```

- [ ] **Step 7: 提交**

```bash
git add services/app-server/app/models/llm.py services/app-server/app/models/__init__.py services/app-server/db/migrations/017_llm_providers.sql services/app-server/tests/test_llm_providers.py
git commit -m "feat(app-server): add llm_providers/llm_models models + migration 017"
```

---

### Task 3: RBAC 权限 `llm:manage` + 迁移 018

**Files:**
- Modify: `services/app-server/app/bootstrap.py`
- Create: `services/app-server/db/migrations/018_llm_manage_perm.sql`
- Test: `services/app-server/tests/test_llm_providers.py`(追加)

- [ ] **Step 1: 追加失败测试(seed 含新权限)**

在 `services/app-server/tests/test_llm_providers.py` 末尾追加:

```python
def test_bootstrap_has_llm_manage(session_factory):
    from app import bootstrap
    from app.models.rbac import Permission, Role
    from sqlalchemy import select
    db = session_factory()
    bootstrap.seed(db)
    assert db.execute(select(Permission).where(Permission.code == "llm:manage")).scalar_one_or_none()
    admin = db.execute(select(Role).where(Role.name == "admin")).scalar_one()
    assert "llm:manage" in [p.code for p in admin.permissions]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_llm_providers.py::test_bootstrap_has_llm_manage -q`
Expected: FAIL(断言 `llm:manage` 不存在)

- [ ] **Step 3: 改 bootstrap.py**

把 `services/app-server/app/bootstrap.py` 的 `PERMISSION_CATALOG` 里 `("apikey:manage", "API Key 管理"),` 那行后面加一行:

```python
    ("apikey:manage", "API Key 管理"),
    ("llm:manage", "LLM 供应商配置"),
```

把 `ADMIN_PERMS` 改为:

```python
ADMIN_PERMS = BUSINESS + ["apikey:manage", "llm:manage"]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_llm_providers.py::test_bootstrap_has_llm_manage -q`
Expected: PASS

- [ ] **Step 5: 写迁移 018**

`services/app-server/db/migrations/018_llm_manage_perm.sql`:

```sql
INSERT INTO permissions (code, description) VALUES
  ('llm:manage', 'LLM 供应商配置')
ON CONFLICT (code) DO NOTHING;

-- llm:manage -> admin(superadmin 持有 '*' 通配,无需单授)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'admin' AND p.code = 'llm:manage'
ON CONFLICT DO NOTHING;
```

- [ ] **Step 6: 提交**

```bash
git add services/app-server/app/bootstrap.py services/app-server/db/migrations/018_llm_manage_perm.sql services/app-server/tests/test_llm_providers.py
git commit -m "feat(app-server): add llm:manage permission + migration 018"
```

---

### Task 4: Schema(掩码输出)

**Files:**
- Create: `services/app-server/app/schemas/llm.py`
- Test: `services/app-server/tests/test_llm_providers.py`(追加)

- [ ] **Step 1: 追加失败测试(掩码序列化,完整 key 不外泄)**

在 `services/app-server/tests/test_llm_providers.py` 末尾追加:

```python
def test_provider_out_masks_key(session_factory):
    from app.models.llm import LlmProvider
    from app.schemas.llm import ProviderOut
    db = session_factory()
    p = LlmProvider(name="x", base_url="u", api_key="sk-supersecret-9999")
    db.add(p); db.commit(); db.refresh(p)
    dumped = ProviderOut.model_validate(p).model_dump()
    assert dumped["masked_key"] == "sk-…9999"
    assert "api_key" not in dumped            # 完整 key 不出 schema
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_llm_providers.py::test_provider_out_masks_key -q`
Expected: FAIL(`ModuleNotFoundError: app.schemas.llm`)

- [ ] **Step 3: 实现 schema**

`services/app-server/app/schemas/llm.py`:

```python
from datetime import datetime
from pydantic import BaseModel


class LlmModelOut(BaseModel):
    id: int
    model_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ProviderCreate(BaseModel):
    name: str
    base_url: str
    api_key: str
    model_ids: list[str] = []


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    enabled: bool | None = None
    api_key: str | None = None   # 留空/None = 不改


class ProviderOut(BaseModel):
    id: int
    name: str
    base_url: str
    masked_key: str              # 读 LlmProvider.masked_key 属性;完整 key 不出现
    enabled: bool
    created_by_name: str | None = None
    created_at: datetime
    models: list[LlmModelOut] = []

    class Config:
        from_attributes = True


class ModelAddIn(BaseModel):
    model_id: str


class TestResult(BaseModel):
    ok: bool
    reply: str | None = None
    latency_ms: int
    error: str | None = None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_llm_providers.py::test_provider_out_masks_key -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/app-server/app/schemas/llm.py services/app-server/tests/test_llm_providers.py
git commit -m "feat(app-server): add llm provider schemas with masked key"
```

---

### Task 5: Service 层(CRUD + 测试)

**Files:**
- Create: `services/app-server/app/services/llm_provider_service.py`
- Test: `services/app-server/tests/test_llm_providers.py`(追加)

- [ ] **Step 1: 追加失败测试**

在 `services/app-server/tests/test_llm_providers.py` 末尾追加:

```python
def test_service_crud_and_models(session_factory):
    from app.services import llm_provider_service as svc
    db = session_factory()
    p = svc.create_provider(db, name="x", base_url="u", api_key="sk-aaaa1111",
                            model_ids=["m1", "m1", "m2"], created_by=None)  # 去重
    assert sorted(m.model_id for m in p.models) == ["m1", "m2"]
    # update: api_key 留空不改,改 name/enabled
    svc.update_provider(db, p.id, name="y", enabled=False, api_key=None)
    db.refresh(p)
    assert p.name == "y" and p.enabled is False and p.api_key == "sk-aaaa1111"
    # update: 给了新 key 则替换
    svc.update_provider(db, p.id, api_key="sk-bbbb2222")
    db.refresh(p); assert p.api_key == "sk-bbbb2222"
    # add model + 重复抛 ValueError
    m = svc.add_model(db, p.id, "m3"); assert m.model_id == "m3"
    import pytest
    with pytest.raises(ValueError):
        svc.add_model(db, p.id, "m3")
    # remove model
    assert svc.remove_model(db, m.id) is True
    # delete provider
    assert svc.delete_provider(db, p.id) is True
    assert svc.delete_provider(db, p.id) is False


def test_service_test_model(session_factory, monkeypatch):
    from app.services import llm_provider_service as svc
    from modelforge_common.llm_client import ChatResult, LLMError
    db = session_factory()
    p = svc.create_provider(db, name="x", base_url="u", api_key="k",
                            model_ids=["m1"], created_by=None)
    mid = p.models[0].id
    # 成功路
    monkeypatch.setattr(svc, "llm_chat",
                        lambda *a, **k: ChatResult(content="2", usage=None, raw={}))
    ok = svc.test_model(db, mid)
    assert ok["ok"] is True and ok["reply"] == "2" and ok["error"] is None
    # 失败路
    def boom(*a, **k):
        raise LLMError(401, "unauthorized")
    monkeypatch.setattr(svc, "llm_chat", boom)
    bad = svc.test_model(db, mid)
    assert bad["ok"] is False and bad["reply"] is None and bad["error"] == "unauthorized"
    # 不存在的 model
    assert svc.test_model(db, 99999) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_llm_providers.py::test_service_crud_and_models tests/test_llm_providers.py::test_service_test_model -q`
Expected: FAIL(`ModuleNotFoundError: app.services.llm_provider_service`)

- [ ] **Step 3: 实现 service**

`services/app-server/app/services/llm_provider_service.py`:

```python
import time
from sqlalchemy import select
from sqlalchemy.orm import Session
from modelforge_common.llm_client import chat as llm_chat, LLMError
from app.models.llm import LlmProvider, LlmModel

PROBE = [{"role": "user", "content": "1+1=? 只回答数字"}]


def create_provider(db: Session, *, name: str, base_url: str, api_key: str,
                    model_ids: list[str], created_by: int | None) -> LlmProvider:
    p = LlmProvider(name=name, base_url=base_url, api_key=api_key, created_by=created_by)
    for mid in dict.fromkeys(model_ids):          # 去重并保序
        p.models.append(LlmModel(model_id=mid))
    db.add(p); db.commit(); db.refresh(p)
    return p


def update_provider(db: Session, provider_id: int, *, name: str | None = None,
                    base_url: str | None = None, enabled: bool | None = None,
                    api_key: str | None = None) -> LlmProvider | None:
    p = db.get(LlmProvider, provider_id)
    if not p:
        return None
    if name is not None:
        p.name = name
    if base_url is not None:
        p.base_url = base_url
    if enabled is not None:
        p.enabled = enabled
    if api_key:                                   # 留空/None -> 保留原 key
        p.api_key = api_key
    db.commit(); db.refresh(p)
    return p


def delete_provider(db: Session, provider_id: int) -> bool:
    p = db.get(LlmProvider, provider_id)
    if not p:
        return False
    db.delete(p); db.commit()                     # cascade delete-orphan 清 models
    return True


def add_model(db: Session, provider_id: int, model_id: str) -> LlmModel | None:
    p = db.get(LlmProvider, provider_id)
    if not p:
        return None
    dup = db.execute(select(LlmModel).where(
        LlmModel.provider_id == provider_id, LlmModel.model_id == model_id)).scalar_one_or_none()
    if dup:
        raise ValueError("该供应商下已存在同名 model_id")
    m = LlmModel(provider_id=provider_id, model_id=model_id)
    db.add(m); db.commit(); db.refresh(m)
    return m


def remove_model(db: Session, model_pk: int) -> bool:
    m = db.get(LlmModel, model_pk)
    if not m:
        return False
    db.delete(m); db.commit()
    return True


def test_model(db: Session, model_pk: int) -> dict | None:
    m = db.get(LlmModel, model_pk)
    if not m:
        return None
    p = m.provider
    t0 = time.monotonic()
    try:
        res = llm_chat(p.base_url, p.api_key, m.model_id, PROBE)
        return {"ok": True, "reply": res.content,
                "latency_ms": int((time.monotonic() - t0) * 1000), "error": None}
    except LLMError as e:
        return {"ok": False, "reply": None,
                "latency_ms": int((time.monotonic() - t0) * 1000), "error": e.message}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_llm_providers.py::test_service_crud_and_models tests/test_llm_providers.py::test_service_test_model -q`
Expected: PASS(2 passed)

- [ ] **Step 5: 提交**

```bash
git add services/app-server/app/services/llm_provider_service.py services/app-server/tests/test_llm_providers.py
git commit -m "feat(app-server): add llm_provider_service (CRUD + connectivity test)"
```

---

### Task 6: `/llm` API 路由 + 注册

**Files:**
- Create: `services/app-server/app/api/llm.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_llm_providers.py`(追加)

- [ ] **Step 1: 追加失败测试(端点 + 鉴权)**

在 `services/app-server/tests/test_llm_providers.py` 末尾追加:

```python
from fastapi.testclient import TestClient


def _client_with(session_factory, codes):
    from app import db as dbmod  # noqa: F401
    db = session_factory()
    u = make_user(db, codes=codes, data_scope="all", email="llm@x.com"); db.close()
    from app.main import app
    return TestClient(app), auth_headers(u.id)


def test_llm_api_crud_and_mask(session_factory, monkeypatch):
    import app.services.llm_provider_service as svc
    from modelforge_common.llm_client import ChatResult
    c, H = _client_with(session_factory, ("llm:manage",))
    # create
    r = c.post("/llm/providers", json={"name": "openai", "base_url": "https://api.x/v1",
               "api_key": "sk-secret-7777", "model_ids": ["gpt-4o-mini"]}, headers=H)
    assert r.status_code == 201
    body = r.json()
    pid = body["id"]
    assert body["masked_key"] == "sk-…7777" and "api_key" not in body
    assert body["models"][0]["model_id"] == "gpt-4o-mini"
    mid = body["models"][0]["id"]
    # list
    listed = c.get("/llm/providers", headers=H).json()
    assert listed and listed[0]["masked_key"] == "sk-…7777"
    # patch: 留空不改 key,改 enabled
    c.patch(f"/llm/providers/{pid}", json={"enabled": False, "api_key": ""}, headers=H)
    assert c.get("/llm/providers", headers=H).json()[0]["enabled"] is False
    # add model + 重复 422
    assert c.post(f"/llm/providers/{pid}/models", json={"model_id": "gpt-4o"}, headers=H).status_code == 201
    assert c.post(f"/llm/providers/{pid}/models", json={"model_id": "gpt-4o"}, headers=H).status_code == 422
    # test endpoint(mock client)
    monkeypatch.setattr(svc, "llm_chat", lambda *a, **k: ChatResult(content="2", usage=None, raw={}))
    tr = c.post(f"/llm/models/{mid}/test", headers=H).json()
    assert tr["ok"] is True and tr["reply"] == "2"
    # delete model + provider
    assert c.delete(f"/llm/models/{mid}", headers=H).status_code == 200
    assert c.delete(f"/llm/providers/{pid}", headers=H).status_code == 200
    assert c.delete(f"/llm/providers/{pid}", headers=H).status_code == 404


def test_llm_api_requires_perm(session_factory):
    c, H = _client_with(session_factory, ("dataset:read",))
    assert c.get("/llm/providers", headers=H).status_code == 403
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_llm_providers.py::test_llm_api_crud_and_mask tests/test_llm_providers.py::test_llm_api_requires_perm -q`
Expected: FAIL(404,路由不存在 / ImportError)

- [ ] **Step 3: 实现路由**

`services/app-server/app/api/llm.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.models.llm import LlmProvider
from app.schemas.llm import (ProviderCreate, ProviderUpdate, ProviderOut,
                             ModelAddIn, LlmModelOut, TestResult)
from app.services import llm_provider_service as svc
from app.pagination import paginate

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(response: Response, page: int | None = Query(None, ge=1),
                   page_size: int = Query(20, ge=1, le=200),
                   _: User = Depends(require("llm:manage")), db: Session = Depends(get_db)):
    stmt = select(LlmProvider).order_by(LlmProvider.id.desc())
    return paginate(db, stmt, response, page, page_size)


@router.post("/providers", response_model=ProviderOut, status_code=201)
def create_provider(body: ProviderCreate, user: User = Depends(require("llm:manage")),
                    db: Session = Depends(get_db)):
    return svc.create_provider(db, name=body.name, base_url=body.base_url,
                               api_key=body.api_key, model_ids=body.model_ids,
                               created_by=user.id)


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
def update_provider(provider_id: int, body: ProviderUpdate,
                    _: User = Depends(require("llm:manage")), db: Session = Depends(get_db)):
    p = svc.update_provider(db, provider_id, name=body.name, base_url=body.base_url,
                            enabled=body.enabled, api_key=body.api_key)
    if not p:
        raise HTTPException(404, "provider not found")
    return p


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: int, _: User = Depends(require("llm:manage")),
                    db: Session = Depends(get_db)):
    if not svc.delete_provider(db, provider_id):
        raise HTTPException(404, "provider not found")
    return {"deleted": True}


@router.post("/providers/{provider_id}/models", response_model=LlmModelOut, status_code=201)
def add_model(provider_id: int, body: ModelAddIn,
              _: User = Depends(require("llm:manage")), db: Session = Depends(get_db)):
    try:
        m = svc.add_model(db, provider_id, body.model_id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not m:
        raise HTTPException(404, "provider not found")
    return m


@router.delete("/models/{model_id}")
def remove_model(model_id: int, _: User = Depends(require("llm:manage")),
                 db: Session = Depends(get_db)):
    if not svc.remove_model(db, model_id):
        raise HTTPException(404, "model not found")
    return {"deleted": True}


@router.post("/models/{model_id}/test", response_model=TestResult)
def test_model(model_id: int, _: User = Depends(require("llm:manage")),
               db: Session = Depends(get_db)):
    result = svc.test_model(db, model_id)
    if result is None:
        raise HTTPException(404, "model not found")
    return result
```

- [ ] **Step 4: 注册路由**

在 `services/app-server/app/main.py` 末尾(`badcase` 注册之后)加:

```python
from app.api import llm
app.include_router(llm.router)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_llm_providers.py -q`
Expected: PASS(全部 llm 测试通过)

- [ ] **Step 6: 跑 app-server 全量回归**

Run: `cd services/app-server && pytest -q`
Expected: PASS(无回归)

- [ ] **Step 7: 提交**

```bash
git add services/app-server/app/api/llm.py services/app-server/app/main.py services/app-server/tests/test_llm_providers.py
git commit -m "feat(app-server): add /llm provider CRUD + test endpoints"
```

---

### Task 7: 前端 API client

**Files:**
- Modify: `frontend/src/api/client.ts`

> 前端无单测工程,验证 = `npx tsc --noEmit`。

- [ ] **Step 1: 加类型与函数**

在 `frontend/src/api/client.ts` 里 `revokeApiKey` 那一行(`export const revokeApiKey = ...`)之后插入:

```typescript
export type LlmModelRow = { id: number; model_id: string; created_at: string };
export type LlmProvider = {
  id: number; name: string; base_url: string; masked_key: string; enabled: boolean;
  created_by_name: string | null; created_at: string; models: LlmModelRow[];
};
export const listLlmProvidersPaged = (p: { page: number; page_size: number }) =>
  getPaginated<LlmProvider>("/llm/providers", p);
export const createLlmProvider = (b: { name: string; base_url: string; api_key: string; model_ids: string[] }) =>
  api.post<LlmProvider>("/llm/providers", b).then(r => r.data);
export const updateLlmProvider = (id: number, b: { name?: string; base_url?: string; enabled?: boolean; api_key?: string }) =>
  api.patch<LlmProvider>(`/llm/providers/${id}`, b).then(r => r.data);
export const deleteLlmProvider = (id: number) => api.delete(`/llm/providers/${id}`).then(r => r.data);
export const addLlmModel = (providerId: number, model_id: string) =>
  api.post<LlmModelRow>(`/llm/providers/${providerId}/models`, { model_id }).then(r => r.data);
export const deleteLlmModel = (modelId: number) => api.delete(`/llm/models/${modelId}`).then(r => r.data);
export type LlmTestResult = { ok: boolean; reply: string | null; latency_ms: number; error: string | null };
export const testLlmModel = (modelId: number) =>
  api.post<LlmTestResult>(`/llm/models/${modelId}/test`).then(r => r.data);
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
Expected: 无错误(exit 0)

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(frontend): add llm provider api client"
```

---

### Task 8: 前端设置页 + 路由 + 导航

**Files:**
- Create: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`

- [ ] **Step 1: 写设置页**

`frontend/src/pages/SettingsPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { SlidersHorizontal, Plus, Trash2, FlaskConical, X, Power } from "lucide-react";
import {
  listLlmProvidersPaged, createLlmProvider, updateLlmProvider, deleteLlmProvider,
  addLlmModel, deleteLlmModel, testLlmModel,
  type LlmProvider, type LlmTestResult,
} from "../api/client";
import {
  Badge, Button, ConfirmDialog, Drawer, EmptyState, Field, Input, Mono,
  PageHeader, Pagination, TableShell, Creator, CreatedAt,
} from "../ui";
import { toastError, toastSuccess } from "../toast";

type TestState = Record<number, "loading" | LlmTestResult>;

export function SettingsPage() {
  const [items, setItems] = useState<LlmProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);

  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState<LlmProvider | null>(null);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelIds, setModelIds] = useState<string[]>([""]);
  const [busy, setBusy] = useState(false);

  const [del, setDel] = useState<LlmProvider | null>(null);
  const [delBusy, setDelBusy] = useState(false);
  const [tests, setTests] = useState<TestState>({});

  const reload = () => listLlmProvidersPaged({ page, page_size: pageSize })
    .then(res => { setItems(res.items); setTotal(res.total); });
  useEffect(() => { setLoading(true); reload().finally(() => setLoading(false)); }, [page, pageSize]);

  const openNew = () => {
    setEdit(null); setName(""); setBaseUrl(""); setApiKey(""); setModelIds([""]);
    setBusy(false); setOpen(true);
  };
  const openEdit = (p: LlmProvider) => {
    setEdit(p); setName(p.name); setBaseUrl(p.base_url); setApiKey(""); setModelIds([]);
    setBusy(false); setOpen(true);
  };

  const submit = async () => {
    setBusy(true);
    try {
      const ids = modelIds.map(s => s.trim()).filter(Boolean);
      if (edit) {
        await updateLlmProvider(edit.id, { name, base_url: baseUrl, ...(apiKey ? { api_key: apiKey } : {}) });
      } else {
        await createLlmProvider({ name, base_url: baseUrl, api_key: apiKey, model_ids: ids });
      }
      setOpen(false); reload();
    } catch {
      toastError("保存失败");
    } finally {
      setBusy(false);
    }
  };

  const toggleEnabled = (p: LlmProvider) =>
    updateLlmProvider(p.id, { enabled: !p.enabled }).then(reload).catch(() => toastError("切换失败"));

  const doDelete = () => {
    if (!del) return;
    setDelBusy(true);
    deleteLlmProvider(del.id).then(() => { setDel(null); reload(); })
      .catch(() => toastError("删除失败")).finally(() => setDelBusy(false));
  };

  const addModel = (p: LlmProvider, mid: string) => {
    const v = mid.trim();
    if (!v) return;
    addLlmModel(p.id, v).then(reload).catch(() => toastError("添加失败(可能重复)"));
  };
  const removeModel = (modelId: number) =>
    deleteLlmModel(modelId).then(reload).catch(() => toastError("删除失败"));
  const runTest = (modelId: number) => {
    setTests(t => ({ ...t, [modelId]: "loading" }));
    testLlmModel(modelId)
      .then(res => setTests(t => ({ ...t, [modelId]: res })))
      .catch(() => setTests(t => ({ ...t, [modelId]: { ok: false, reply: null, latency_ms: 0, error: "请求失败" } })));
  };

  return (
    <>
      <PageHeader
        title="设置"
        subtitle="配置 OpenAI 协议的大模型供应商(下挂多个 model-id),供 Prompt 评测选用。"
        actions={<Button variant="primary" onClick={openNew}><Plus size={16} /> 新建供应商</Button>}
      />

      <TableShell
        loading={loading}
        empty={items.length === 0}
        head={<><th>名称</th><th>base_url</th><th>API Key</th><th>模型</th><th>状态</th><th>创建者</th><th className="w-36">创建时间</th><th className="w-44 text-right"></th></>}
      >
        {items.length === 0 ? (
          <EmptyState icon={<SlidersHorizontal size={22} />} title="还没有供应商" hint="新建一个大模型供应商,填 base_url / api_key / model-id。" />
        ) : items.map(p => (
          <tr key={p.id} className="align-top">
            <td className="font-medium text-slate-800">{p.name}</td>
            <td><Mono>{p.base_url}</Mono></td>
            <td><Mono>{p.masked_key}</Mono></td>
            <td className="wrap">
              <div className="flex flex-col gap-1.5">
                {p.models.map(m => {
                  const st = tests[m.id];
                  return (
                    <div key={m.id} className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <Mono>{m.model_id}</Mono>
                        <Button size="sm" loading={st === "loading"} onClick={() => runTest(m.id)}>
                          <FlaskConical size={12} /> 测试
                        </Button>
                        <button onClick={() => removeModel(m.id)} className="text-slate-400 hover:text-red-500" title="删除该 model">
                          <X size={13} />
                        </button>
                      </div>
                      {st && st !== "loading" && (
                        <div className={`text-[12px] ${st.ok ? "text-emerald-600" : "text-red-600"}`}>
                          {st.ok ? `✓ ${st.reply}` : `✗ ${st.error}`}<span className="ml-1 text-slate-400">{st.latency_ms}ms</span>
                        </div>
                      )}
                    </div>
                  );
                })}
                <AddModelInline onAdd={mid => addModel(p, mid)} />
              </div>
            </td>
            <td>
              <button onClick={() => toggleEnabled(p)} title="点击切换">
                <Badge tone={p.enabled ? "green" : "gray"}><Power size={11} /> {p.enabled ? "启用" : "停用"}</Badge>
              </button>
            </td>
            <td><Creator name={p.created_by_name} /></td>
            <td><CreatedAt at={p.created_at} /></td>
            <td className="text-right">
              <div className="flex items-center justify-end gap-2">
                <Button size="sm" onClick={() => openEdit(p)}>编辑</Button>
                <Button size="sm" variant="danger" onClick={() => setDel(p)}><Trash2 size={13} /></Button>
              </div>
            </td>
          </tr>
        ))}
      </TableShell>
      <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title={edit ? "编辑供应商" : "新建供应商"}
        subtitle="OpenAI 协议:base_url 形如 https://api.openai.com/v1。"
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button variant="subtle" disabled={busy} onClick={() => setOpen(false)}>取消</Button>
            <Button variant="primary" disabled={!name || !baseUrl || (!edit && !apiKey)} loading={busy} onClick={submit}>保存</Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="名称"><Input value={name} onChange={e => setName(e.target.value)} placeholder="OpenAI 官方 / 内网 vLLM" /></Field>
          <Field label="base_url"><Input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" /></Field>
          <Field label={edit ? "API Key(留空=不修改)" : "API Key"}>
            <Input value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder={edit ? p_mask(edit) : "sk-…"} />
          </Field>
          {!edit && (
            <Field label="model-id(可多个)">
              <div className="flex flex-col gap-2">
                {modelIds.map((m, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Input value={m} onChange={e => setModelIds(arr => arr.map((x, j) => j === i ? e.target.value : x))} placeholder="gpt-4o-mini" />
                    {modelIds.length > 1 && (
                      <button onClick={() => setModelIds(arr => arr.filter((_, j) => j !== i))} className="text-slate-400 hover:text-red-500"><X size={15} /></button>
                    )}
                  </div>
                ))}
                <button onClick={() => setModelIds(arr => [...arr, ""])} className="self-start text-[13px] text-brand-600 hover:underline">+ 再加一个</button>
              </div>
            </Field>
          )}
          {edit && <p className="text-[12px] text-slate-400">model-id 在列表里逐个增删。</p>}
        </div>
      </Drawer>

      <ConfirmDialog
        open={del !== null}
        title="删除供应商"
        message={<>确定删除供应商 <b className="text-slate-700">{del?.name}</b>?其下所有 model-id 一并删除。</>}
        busy={delBusy}
        onCancel={() => setDel(null)}
        onConfirm={doDelete}
      />
    </>
  );
}

function p_mask(p: LlmProvider) { return p.masked_key || "sk-…"; }

function AddModelInline({ onAdd }: { onAdd: (mid: string) => void }) {
  const [v, setV] = useState("");
  return (
    <div className="flex items-center gap-2 pt-1">
      <Input value={v} onChange={e => setV(e.target.value)} placeholder="新增 model-id" className="h-7 w-40 text-[12px]"
             onKeyDown={e => { if (e.key === "Enter") { onAdd(v); setV(""); } }} />
      <button onClick={() => { onAdd(v); setV(""); }} className="text-[12px] text-brand-600 hover:underline">添加</button>
    </div>
  );
}
```

- [ ] **Step 2: 注册路由**

在 `frontend/src/App.tsx` 顶部 import 段加(与其它 page import 同处):

```tsx
import { SettingsPage } from "./pages/SettingsPage";
```

在 `else if (path === "/api-keys") page = <ApiKeysPage />;` 之后加一行:

```tsx
  else if (path === "/settings") page = <SettingsPage />;
```

- [ ] **Step 3: 加导航项**

在 `frontend/src/components/AppShell.tsx`:lucide-react 的 import 里加 `SlidersHorizontal`;在 `NAV` 数组里 `api-keys` 那一项之后加:

```tsx
  { href: "/settings", label: "设置", icon: <SlidersHorizontal size={18} />, perm: "llm:manage", match: p => p.startsWith("/settings") },
```

- [ ] **Step 4: 类型检查 + 构建**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm run build`
Expected: 无类型错误,构建成功

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/SettingsPage.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx
git commit -m "feat(frontend): add LLM provider settings page"
```

---

## 收尾验证(全部任务后)

- [ ] 跑全量后端测试:`cd services/common && pytest -q` 与 `cd services/app-server && pytest -q`,全绿。
- [ ] 前端 `npx tsc --noEmit -p tsconfig.app.json` 与 `npm run build` 通过。
- [ ] 手动冒烟:重启 app-server(迁移 017/018 自动应用)→ 用 admin 登录 → 「设置」可见 → 新建供应商(填真实 base_url/key/model-id)→ 点 model 的「测试」看到回复 → 编辑留空不改 key、列表 key 始终掩码 → 删除级联。
- [ ] 用无 `llm:manage` 的账号登录,确认看不到「设置」入口,直接 `GET /llm/providers` 返回 403。

---

## 自审记录(写计划后对照 spec)

- **Spec 覆盖**:数据模型(T2)、迁移 017/018(T2/T3)、共享 llm_client(T1)、`/llm` 全部端点(T6)、掩码(T4/T5/T6)、RBAC `llm:manage`(T3)、设置页前端(T7/T8)、错误处理(test 端点 ok 字段 + 422 重复 + 404 + LLMError 归一化,见 T5/T6)、测试(各任务 TDD + 收尾回归)。无遗漏。
- **占位符**:无 TBD/TODO;每个代码步给了完整代码与确切命令。
- **类型一致**:`mask_key` → `masked_key` 属性 → `ProviderOut.masked_key` 一致;service 函数名(`create_provider/update_provider/delete_provider/add_model/remove_model/test_model`)在 T5 定义、T6 调用一致;`llm_chat` 别名在 service 内定义并被测试 monkeypatch 一致;前端 `LlmProvider/LlmModelRow/LlmTestResult` 类型在 T7 定义、T8 使用一致。
