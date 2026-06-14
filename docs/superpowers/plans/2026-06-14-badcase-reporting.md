# Badcase 上报与修复闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地“上线 → 发现 badcase → API 上报 → 标注 → 重训修复”闭环,并新增一套通用 API Key 体系,既给上报接口、也给 model-server 推理接口鉴权。

**Architecture:** badcase 作为 app-server 一等实体,复用现有 dataset/training/RBAC。API Key 存储与校验只在 app-server(单一事实源);model-server 推理接口通过调用 app-server 内部校验端点(带 60s 内存缓存)强制 `X-Api-Key`。标注后的 badcase 一键生成 `badcase-` 前缀训练集,复用现有训练流(多数据集合并)做修复。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + 编号 SQL 迁移(app-server)、FastAPI(model-server)、React + Vite + TS(frontend)、pytest。

**Spec:** `docs/superpowers/specs/2026-06-14-badcase-reporting-design.md`

---

## 约定与现有模式(执行前必读)

- **铁律**:任何改 `services/app-server/app/models/**` 必须在同次提交里加一个**下一个编号**的 `services/app-server/db/migrations/NNN_*.sql`(幂等:`CREATE TABLE IF NOT EXISTS`、`INSERT ... ON CONFLICT DO NOTHING`)。当前最大编号是 `010`,本计划新增 `011`–`014`。
- **测试 DB**:`tests/conftest.py` 用 SQLite + `Base.metadata.create_all`(不跑编号 SQL),并已关 `run_migrations_on_startup`。助手:`make_user(db, codes=(...), data_scope=..., email=...)`、`auth_headers(user_id)`、`session_factory` fixture。
- **跑测试**:`cd services/app-server && python -m pytest -q`(本机 python 即 miniconda,已装依赖);`cd services/model-server && python -m pytest -q`。
- **鉴权依赖**:`require("perm:code")`(app/authz.py)做权限;`require_internal_token`(app/auth.py)做服务间;`apply_scope(stmt, Model, user)` 做数据范围。
- **RBAC 一致性**:改权限目录要同时改 `app/bootstrap.py`(`PERMISSION_CATALOG` / 角色授权)与对应编号迁移。
- **model-server 信封**:所有响应 `{code, data, message}`,HTTP 状态码保留。
- **提交**:每个 Task 末尾 commit;不 push。提交信息以 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` 结尾。

## File Structure(新增/修改)

**app-server**
- Create `app/models/api_key.py` — `ApiKey` ORM。
- Create `app/services/api_key_service.py` — 生成/hash/校验/列表/吊销。
- Create `app/api_key_auth.py` — `require_api_key(scope)` FastAPI 依赖(供上报端点用)。
- Create `app/schemas/api_key.py` — 入参/出参。
- Create `app/api/api_keys.py` — `/api-keys` 管理 + `/internal/api-keys/verify`。
- Create `app/models/badcase.py` — `Badcase` ORM。
- Create `app/badcase_contracts.py` — 四类任务的 input/annotation 校验 + 训练行映射 + rules/category。
- Create `app/services/badcase_service.py` — report / annotate / build_dataset。
- Create `app/schemas/badcase.py` — 入参/出参。
- Create `app/api/badcase.py` — `/badcase/report`、`/badcase/rules`、`/badcases*`。
- Create migrations `011_api_keys.sql`、`012_api_key_perm.sql`、`013_badcases.sql`、`014_badcase_perms.sql`。
- Modify `app/bootstrap.py` — 加 `apikey:manage`、`badcase:read`、`badcase:annotate` 到目录与角色。
- Modify `app/main.py` — 注册新 router。
- Tests:`tests/test_api_keys.py`、`tests/test_badcase_contracts.py`、`tests/test_badcase_api.py`、`tests/test_badcase_build_dataset.py`、`tests/test_bootstrap.py`(更新计数)、`tests/test_migrations_apply.py`(如断言迁移数量则更新)。

**model-server**
- Modify `server/config.py` — 加 `app_server_url`、`internal_token`。
- Create `server/api_auth.py` — `require_api_key` 依赖(TTL 缓存 + 调 app-server verify)。
- Modify `server/main.py` — `/predict`、`/embed`、`/similarity` 加依赖。
- Tests:`tests/test_api_auth.py`、更新 `tests/test_server_api.py`(请求带 key)。

**frontend**
- Modify `src/api/client.ts` — ApiKey/Badcase 类型 + 接口函数。
- Create `src/pages/ApiKeysPage.tsx`、`src/pages/BadcasePage.tsx`、`src/pages/BadcaseRulesPage.tsx`。
- Modify `src/components/AppShell.tsx`(NAV)、`src/App.tsx`(路由)、`src/apiDocs.ts`(curl 加 `X-Api-Key`)。

---

# Phase 1 — 通用 API Key 系统

### Task 1.1: `ApiKey` 模型 + 迁移 011

**Files:**
- Create: `services/app-server/app/models/api_key.py`
- Modify: `services/app-server/app/models/__init__.py`（若它显式 import 各模型则补上 ApiKey）
- Create: `services/app-server/db/migrations/011_api_keys.sql`
- Test: `services/app-server/tests/test_api_keys.py`

- [ ] **Step 1: 写失败测试(模型可建表可插入)**

```python
# services/app-server/tests/test_api_keys.py
def test_api_key_model_roundtrip(session_factory):
    from app.models.api_key import ApiKey
    db = session_factory()
    k = ApiKey(name="svc", key_prefix="mf_abc123", key_hash="deadbeef",
               scopes=["badcase:report", "inference"])
    db.add(k); db.commit(); db.refresh(k)
    assert k.id and k.revoked_at is None and "inference" in k.scopes
```

- [ ] **Step 2: 跑测试看它失败**

Run: `cd services/app-server && python -m pytest tests/test_api_keys.py::test_api_key_model_roundtrip -q`
Expected: FAIL（`ModuleNotFoundError: app.models.api_key`）

- [ ] **Step 3: 写模型**

```python
# services/app-server/app/models/api_key.py
from datetime import datetime
from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    key_prefix: Mapped[str] = mapped_column()          # "mf_" + 8 chars, for display
    key_hash: Mapped[str] = mapped_column(unique=True)  # sha256 of full plaintext key
    scopes: Mapped[list] = mapped_column(JSON, default=list)  # ["inference","badcase:report"]
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

确认 `app/models/__init__.py` 能让 `Base.metadata` 发现该表(若该文件逐个 import 模型,加 `from app.models.api_key import ApiKey  # noqa`)。

- [ ] **Step 4: 写编号迁移 011**

```sql
-- services/app-server/db/migrations/011_api_keys.sql
-- Shared API keys (for badcase report + model-server inference auth). Plaintext key
-- is shown once at creation; only its sha256 hash is stored.
CREATE TABLE IF NOT EXISTS api_keys (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    key_prefix    TEXT NOT NULL,
    key_hash      TEXT NOT NULL UNIQUE,
    scopes        JSON NOT NULL DEFAULT '[]',
    created_by    INTEGER REFERENCES users(id),
    last_used_at  TIMESTAMP,
    revoked_at    TIMESTAMP,
    created_at    TIMESTAMP DEFAULT now(),
    updated_at    TIMESTAMP DEFAULT now()
);
```

- [ ] **Step 5: 跑测试看通过**

Run: `cd services/app-server && python -m pytest tests/test_api_keys.py::test_api_key_model_roundtrip -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/app-server/app/models/api_key.py services/app-server/app/models/__init__.py services/app-server/db/migrations/011_api_keys.sql services/app-server/tests/test_api_keys.py
git commit -m "feat(api-key): ApiKey model + migration 011"
```

---

### Task 1.2: API Key service(生成/hash/校验/列表/吊销)

**Files:**
- Create: `services/app-server/app/services/api_key_service.py`
- Test: `services/app-server/tests/test_api_keys.py`（追加)

- [ ] **Step 1: 写失败测试**

```python
# append to services/app-server/tests/test_api_keys.py
def test_api_key_service_create_verify_revoke(session_factory):
    from app.services import api_key_service as svc
    db = session_factory()
    plaintext, key = svc.create_key(db, name="svc", scopes=["badcase:report"], created_by=None)
    assert plaintext.startswith("mf_") and key.key_prefix == plaintext[:11]
    # plaintext never stored
    assert key.key_hash == svc.hash_key(plaintext) and key.key_hash != plaintext
    # verify: correct key + scope -> returns the key
    assert svc.verify(db, plaintext, "badcase:report").id == key.id
    # wrong scope -> None
    assert svc.verify(db, plaintext, "inference") is None
    # unknown key -> None
    assert svc.verify(db, "mf_nope", "badcase:report") is None
    # revoke -> None
    svc.revoke(db, key.id)
    assert svc.verify(db, plaintext, "badcase:report") is None
```

- [ ] **Step 2: 跑测试看它失败**

Run: `cd services/app-server && python -m pytest tests/test_api_keys.py::test_api_key_service_create_verify_revoke -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 写 service**

```python
# services/app-server/app/services/api_key_service.py
import hashlib
import secrets
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.api_key import ApiKey


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def create_key(db: Session, *, name: str, scopes: list[str],
               created_by: int | None) -> tuple[str, ApiKey]:
    """Returns (plaintext, ApiKey). Plaintext is shown once and never stored."""
    plaintext = "mf_" + secrets.token_urlsafe(24)
    key = ApiKey(name=name, key_prefix=plaintext[:11], key_hash=hash_key(plaintext),
                 scopes=list(scopes), created_by=created_by)
    db.add(key); db.commit(); db.refresh(key)
    return plaintext, key


def verify(db: Session, plaintext: str, scope: str) -> ApiKey | None:
    if not plaintext:
        return None
    key = db.execute(select(ApiKey).where(ApiKey.key_hash == hash_key(plaintext))).scalar_one_or_none()
    if not key or key.revoked_at is not None or scope not in (key.scopes or []):
        return None
    key.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return key


def list_keys(db: Session) -> list[ApiKey]:
    return list(db.execute(select(ApiKey).order_by(ApiKey.id.desc())).scalars())


def revoke(db: Session, key_id: int) -> bool:
    key = db.get(ApiKey, key_id)
    if not key or key.revoked_at is not None:
        return False
    key.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return True
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd services/app-server && python -m pytest tests/test_api_keys.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add services/app-server/app/services/api_key_service.py services/app-server/tests/test_api_keys.py
git commit -m "feat(api-key): key service (create/verify/revoke, sha256 hash)"
```

---

### Task 1.3: `apikey:manage` 权限 + 迁移 012 + bootstrap

**Files:**
- Create: `services/app-server/db/migrations/012_api_key_perm.sql`
- Modify: `services/app-server/app/bootstrap.py`
- Test: `services/app-server/tests/test_bootstrap.py`

- [ ] **Step 1: 更新 bootstrap 计数测试**

先看现有断言:`grep -n "PERMISSION_CATALOG\|len(\|nperm\|== 1" services/app-server/tests/test_bootstrap.py`。把权限总数断言 +1(`apikey:manage`)。例如把 `assert len(catalog) == 13` 改为 `14`,并新增:

```python
# in services/app-server/tests/test_bootstrap.py — after seed(db)
def test_apikey_manage_seeded(session_factory):
    from app.bootstrap import seed
    from app.models.rbac import Permission, Role
    from sqlalchemy import select
    db = session_factory(); seed(db)
    assert db.execute(select(Permission).where(Permission.code == "apikey:manage")).scalar_one_or_none()
    admin = db.execute(select(Role).where(Role.name == "admin")).scalar_one()
    assert "apikey:manage" in {p.code for p in admin.permissions}
```

- [ ] **Step 2: 跑测试看它失败**

Run: `cd services/app-server && python -m pytest tests/test_bootstrap.py -q`
Expected: FAIL（apikey:manage 未 seed）

- [ ] **Step 3: 改 bootstrap**

在 `PERMISSION_CATALOG` 加一项,并把 `apikey:manage` 授予 admin(不给 member/viewer);superadmin 有 `*` 自动覆盖:

```python
# services/app-server/app/bootstrap.py
PERMISSION_CATALOG = [
    ("dataset:read", "看数据集/版本"), ("dataset:write", "建数据集/传版本"),
    ("training:read", "看训练任务"), ("training:run", "发起训练"),
    ("model:read", "看模型版本"), ("model:write", "管理模型(提升阶段)"),
    ("eval:read", "看评估"), ("eval:run", "发起评估"),
    ("deploy:read", "看部署"), ("deploy:write", "部署/停止"),
    ("user:manage", "用户管理"), ("role:manage", "角色管理"),
    ("apikey:manage", "API Key 管理"),
    ("*", "通配"),
]
READS = ["dataset:read", "training:read", "model:read", "eval:read", "deploy:read"]
BUSINESS = READS + ["dataset:write", "training:run", "eval:run", "deploy:write", "model:write"]
ADMIN_PERMS = BUSINESS + ["apikey:manage"]
SYSTEM_ROLES = [
    ("superadmin", "超级管理员", "all", True, ["*"]),
    ("admin", "管理员", "all", False, ADMIN_PERMS),
    ("member", "成员", "own", False, BUSINESS),
    ("viewer", "只读", "own", False, READS),
]
```

- [ ] **Step 4: 写迁移 012**

```sql
-- services/app-server/db/migrations/012_api_key_perm.sql
INSERT INTO permissions (code, description)
VALUES ('apikey:manage', 'API Key 管理')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'admin' AND p.code = 'apikey:manage'
ON CONFLICT DO NOTHING;
```

- [ ] **Step 5: 跑测试看通过**

Run: `cd services/app-server && python -m pytest tests/test_bootstrap.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/app-server/app/bootstrap.py services/app-server/db/migrations/012_api_key_perm.sql services/app-server/tests/test_bootstrap.py
git commit -m "feat(api-key): apikey:manage permission + migration 012 + bootstrap"
```

---

### Task 1.4: API Key 管理 API + 内部校验端点

**Files:**
- Create: `services/app-server/app/schemas/api_key.py`
- Create: `services/app-server/app/api/api_keys.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_api_keys.py`（追加 API 测试)

- [ ] **Step 1: 写失败测试(API 流)**

```python
# append to services/app-server/tests/test_api_keys.py
from fastapi.testclient import TestClient

def _client_with(session_factory, codes):
    from app import db as dbmod
    db = session_factory()  # creates tables + sets SessionLocal via fixture
    from tests.conftest import make_user, auth_headers
    u = make_user(db, codes=codes, data_scope="all", email="ak@x.com"); db.close()
    from app.main import app
    return TestClient(app), auth_headers(u.id)

def test_api_keys_endpoints(session_factory):
    c, H = _client_with(session_factory, ("apikey:manage",))
    r = c.post("/api-keys", json={"name": "svc", "scopes": ["badcase:report"]}, headers=H)
    assert r.status_code == 201
    body = r.json()
    assert body["plaintext"].startswith("mf_")          # shown once
    assert "key_hash" not in body and "plaintext" not in c.get("/api-keys", headers=H).json()[0]
    kid = body["id"]
    # internal verify
    v = c.post("/internal/api-keys/verify",
               json={"key": body["plaintext"], "scope": "badcase:report"},
               headers={"X-Internal-Token": "modelforge-internal"})
    assert v.status_code == 200 and v.json()["valid"] is True
    # revoke -> verify false
    assert c.delete(f"/api-keys/{kid}", headers=H).status_code == 200
    v2 = c.post("/internal/api-keys/verify",
                json={"key": body["plaintext"], "scope": "badcase:report"},
                headers={"X-Internal-Token": "modelforge-internal"})
    assert v2.json()["valid"] is False

def test_api_keys_requires_perm(session_factory):
    c, H = _client_with(session_factory, ("dataset:read",))
    assert c.get("/api-keys", headers=H).status_code == 403
```

- [ ] **Step 2: 跑测试看它失败**

Run: `cd services/app-server && python -m pytest tests/test_api_keys.py -k endpoints -q`
Expected: FAIL（404 路由不存在）

- [ ] **Step 3: 写 schemas**

```python
# services/app-server/app/schemas/api_key.py
from datetime import datetime
from pydantic import BaseModel

VALID_SCOPES = {"inference", "badcase:report"}

class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = []

class ApiKeyOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    created_by_name: str | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    class Config: from_attributes = True

class ApiKeyCreated(ApiKeyOut):
    plaintext: str   # one-time secret

class VerifyIn(BaseModel):
    key: str
    scope: str
```

注:`created_by_name` 复用不了 CreatorMixin(ApiKey 未继承它)。在 `_out` 里手动塞 None,或给 ApiKey 加 CreatorMixin。**决策**:给 `ApiKey` 继承 `CreatorMixin`(与其它表一致),则 `created_by_name` 自动可用——回到 Task 1.1 模型,把 `class ApiKey(Base, TimestampMixin):` 改为 `class ApiKey(Base, TimestampMixin, CreatorMixin):`(若已实现则在本步顺手改并补一行 import)。

- [ ] **Step 4: 写 API + 内部端点**

```python
# services/app-server/app/api/api_keys.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.auth import require_internal_token
from app.models.user import User
from app.schemas.api_key import ApiKeyCreate, ApiKeyOut, ApiKeyCreated, VerifyIn, VALID_SCOPES
from app.services import api_key_service

router = APIRouter(prefix="/api-keys", tags=["api-keys"])
internal_router = APIRouter(tags=["api-keys-internal"])


@router.get("", response_model=list[ApiKeyOut])
def list_keys(_: User = Depends(require("apikey:manage")), db: Session = Depends(get_db)):
    return api_key_service.list_keys(db)


@router.post("", response_model=ApiKeyCreated, status_code=201)
def create_key(body: ApiKeyCreate, user: User = Depends(require("apikey:manage")),
               db: Session = Depends(get_db)):
    bad = [s for s in body.scopes if s not in VALID_SCOPES]
    if bad or not body.scopes:
        raise HTTPException(422, f"scopes must be a non-empty subset of {sorted(VALID_SCOPES)}")
    plaintext, key = api_key_service.create_key(db, name=body.name, scopes=body.scopes,
                                                created_by=user.id)
    out = ApiKeyCreated.model_validate(key).model_copy(update={"plaintext": plaintext})
    return out


@router.delete("/{key_id}")
def revoke_key(key_id: int, _: User = Depends(require("apikey:manage")),
               db: Session = Depends(get_db)):
    if not api_key_service.revoke(db, key_id):
        raise HTTPException(404, "key not found or already revoked")
    return {"revoked": True}


@internal_router.post("/internal/api-keys/verify",
                      dependencies=[Depends(require_internal_token)])
def verify_key(body: VerifyIn, db: Session = Depends(get_db)):
    key = api_key_service.verify(db, body.key, body.scope)
    return {"valid": key is not None, "key_id": key.id if key else None,
            "name": key.name if key else None}
```

- [ ] **Step 5: 注册 router**

```python
# services/app-server/app/main.py — after the users router block
from app.api import api_keys
app.include_router(api_keys.router)
app.include_router(api_keys.internal_router)
```

- [ ] **Step 6: 跑测试看通过**

Run: `cd services/app-server && python -m pytest tests/test_api_keys.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/app-server/app/schemas/api_key.py services/app-server/app/api/api_keys.py services/app-server/app/main.py services/app-server/app/models/api_key.py services/app-server/tests/test_api_keys.py
git commit -m "feat(api-key): management API + internal verify endpoint"
```

---

### Task 1.5: 前端 API Key 页 + 客户端 + 导航

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/ApiKeysPage.tsx`
- Modify: `frontend/src/components/AppShell.tsx`、`frontend/src/App.tsx`

- [ ] **Step 1: 客户端类型与函数**

```ts
// frontend/src/api/client.ts — append near other types
export type ApiKey = { id: number; name: string; key_prefix: string; scopes: string[]; created_by_name: string | null; last_used_at: string | null; revoked_at: string | null; created_at: string };
export const listApiKeys = () => api.get<ApiKey[]>("/api-keys").then(r => r.data);
export const createApiKey = (b: { name: string; scopes: string[] }) => api.post<ApiKey & { plaintext: string }>("/api-keys", b).then(r => r.data);
export const revokeApiKey = (id: number) => api.delete(`/api-keys/${id}`).then(r => r.data);
```

- [ ] **Step 2: 页面(列表 + 新建抽屉 + 一次性明文弹框 + 吊销确认)**

```tsx
// frontend/src/pages/ApiKeysPage.tsx
import { useEffect, useState } from "react";
import { KeyRound, Plus, Copy, Check, Ban } from "lucide-react";
import { listApiKeys, createApiKey, revokeApiKey, type ApiKey } from "../api/client";
import { Badge, Button, ConfirmDialog, Drawer, EmptyState, Field, Input, Mono, PageHeader, TableShell, Creator, CreatedAt } from "../ui";
import { toastError, toastSuccess } from "../toast";

const SCOPES = [
  { code: "inference", label: "推理调用(/predict /embed /similarity)" },
  { code: "badcase:report", label: "Badcase 上报(/badcase/report)" },
];

export function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>([]);
  const [created, setCreated] = useState<string | null>(null);  // one-time plaintext
  const [copied, setCopied] = useState(false);
  const [revoke, setRevoke] = useState<ApiKey | null>(null);
  const [revBusy, setRevBusy] = useState(false);
  const reload = () => listApiKeys().then(setKeys);
  useEffect(() => { reload().finally(() => setLoading(false)); }, []);

  const openDrawer = () => { setName(""); setScopes([]); setBusy(false); setOpen(true); };
  const toggle = (c: string) => setScopes(s => s.includes(c) ? s.filter(x => x !== c) : [...s, c]);
  const submit = () => {
    setBusy(true);
    createApiKey({ name, scopes }).then(k => { setOpen(false); setCreated(k.plaintext); setCopied(false); reload(); })
      .catch(() => toastError("创建失败")).finally(() => setBusy(false));
  };
  const doRevoke = () => {
    if (!revoke) return;
    setRevBusy(true);
    revokeApiKey(revoke.id).then(() => { setRevoke(null); reload(); })
      .catch(() => toastError("吊销失败")).finally(() => setRevBusy(false));
  };

  return (
    <>
      <PageHeader title="API Key" subtitle="对外鉴权令牌:用于在线推理调用与 Badcase 上报。明文仅在创建时显示一次。"
        actions={<Button variant="primary" onClick={openDrawer}><Plus size={16} /> 新建 Key</Button>} />

      <TableShell loading={loading} empty={keys.length === 0}
        head={<><th>名称</th><th>前缀</th><th>权限范围</th><th>状态</th><th>创建者</th><th className="w-36">创建时间</th><th className="w-20 text-right"></th></>}>
        {keys.length === 0 ? <EmptyState icon={<KeyRound size={22} />} title="还没有 API Key" /> :
          keys.map(k => (
            <tr key={k.id}>
              <td className="font-medium text-slate-800">{k.name}</td>
              <td><Mono>{k.key_prefix}…</Mono></td>
              <td><div className="flex flex-wrap gap-1">{k.scopes.map(s => <span key={s} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600">{s}</span>)}</div></td>
              <td>{k.revoked_at ? <Badge tone="gray" dot>已吊销</Badge> : <Badge tone="green" dot>有效</Badge>}</td>
              <td><Creator name={k.created_by_name} /></td>
              <td><CreatedAt at={k.created_at} /></td>
              <td className="text-right">{!k.revoked_at && <Button size="sm" variant="danger" onClick={() => setRevoke(k)}><Ban size={13} /> 吊销</Button>}</td>
            </tr>
          ))}
      </TableShell>

      <Drawer open={open} onClose={() => setOpen(false)} title="新建 API Key"
        subtitle="选择该 Key 可用于哪些接口。创建后请立即复制保存明文,之后无法再查看。"
        footer={<div className="flex items-center justify-end gap-2">
          <Button variant="subtle" disabled={busy} onClick={() => setOpen(false)}>取消</Button>
          <Button variant="primary" disabled={!name || scopes.length === 0} loading={busy} onClick={submit}><Plus size={16} /> 创建</Button>
        </div>}>
        <div className="flex flex-col gap-4">
          <Field label="名称"><Input placeholder="如 客服系统-生产" value={name} onChange={e => setName(e.target.value)} /></Field>
          <div>
            <div className="label mb-1.5">权限范围</div>
            <div className="flex flex-col gap-1.5">
              {SCOPES.map(s => (
                <label key={s.code} onClick={() => toggle(s.code)}
                  className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 ${scopes.includes(s.code) ? "border-brand-300 bg-brand-50" : "border-slate-200 hover:border-slate-300"}`}>
                  <span className={`flex h-4 w-4 items-center justify-center rounded border ${scopes.includes(s.code) ? "border-brand-500 bg-brand-500 text-white" : "border-slate-300"}`}>{scopes.includes(s.code) && <Check size={12} strokeWidth={3} />}</span>
                  <span className="font-mono text-[12.5px] text-slate-700">{s.code}</span>
                  <span className="ml-auto text-[11.5px] text-slate-400">{s.label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
      </Drawer>

      {/* one-time plaintext dialog */}
      <ConfirmDialog open={created !== null} title="API Key 已创建" confirmText="我已保存"
        message={<div className="flex flex-col gap-2">
          <div className="text-[13px] text-slate-600">请立即复制保存,关闭后将无法再次查看:</div>
          <div className="flex items-center gap-2 rounded-lg bg-slate-900 p-3">
            <Mono className="flex-1 break-all text-slate-100">{created}</Mono>
            <Button size="sm" onClick={() => { navigator.clipboard.writeText(created!); setCopied(true); toastSuccess("已复制"); }}>
              {copied ? <Check size={13} /> : <Copy size={13} />}
            </Button>
          </div>
        </div>}
        onCancel={() => setCreated(null)} onConfirm={() => setCreated(null)} />

      <ConfirmDialog open={revoke !== null} title="吊销 API Key" confirmText="吊销" busy={revBusy}
        message={<>确定吊销 <b className="text-slate-700">{revoke?.name}</b>?吊销后该 Key 立即失效(model-server 缓存最长 60 秒生效)。</>}
        onCancel={() => setRevoke(null)} onConfirm={doRevoke} />
    </>
  );
}
```

- [ ] **Step 3: 导航 + 路由**

```tsx
// frontend/src/components/AppShell.tsx — add import KeyRound from lucide-react, then in NAV (after roles):
{ href: "/api-keys", label: "API Key", icon: <KeyRound size={18} />, perm: "apikey:manage", match: p => p.startsWith("/api-keys") },
```

```tsx
// frontend/src/App.tsx — import + route
import { ApiKeysPage } from "./pages/ApiKeysPage";
// ...in the else-if chain:
else if (path === "/api-keys") page = <ApiKeysPage />;
```

- [ ] **Step 4: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建通过(无 TS 错误)。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/ApiKeysPage.tsx frontend/src/components/AppShell.tsx frontend/src/App.tsx
git commit -m "feat(api-key): API Keys management page + nav"
```

---

# Phase 2 — model-server 推理鉴权

### Task 2.1: model-server `require_api_key` 依赖(TTL 缓存 + 调 verify)

**Files:**
- Modify: `services/model-server/server/config.py`
- Create: `services/model-server/server/api_auth.py`
- Test: `services/model-server/tests/test_api_auth.py`

- [ ] **Step 1: 写失败测试**

```python
# services/model-server/tests/test_api_auth.py
import time
import pytest
from fastapi import HTTPException
import server.api_auth as auth

def test_require_api_key_valid_and_cached(monkeypatch):
    auth._CACHE.clear()
    calls = {"n": 0}
    def fake_verify(key, scope):
        calls["n"] += 1
        return key == "good"
    monkeypatch.setattr(auth, "_remote_verify", fake_verify)
    dep = auth.require_api_key("inference")
    assert dep(x_api_key="good") is None          # passes
    assert dep(x_api_key="good") is None           # cache hit
    assert calls["n"] == 1                          # only one remote call
    with pytest.raises(HTTPException) as e:
        dep(x_api_key="bad")
    assert e.value.status_code == 401
    with pytest.raises(HTTPException):
        dep(x_api_key=None)                         # missing key
```

- [ ] **Step 2: 跑测试看它失败**

Run: `cd services/model-server && python -m pytest tests/test_api_auth.py -q`
Expected: FAIL（`ModuleNotFoundError: server.api_auth`）

- [ ] **Step 3: config 加字段**

```python
# services/model-server/server/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mlflow_tracking_uri: str = "http://localhost:5000"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    app_server_url: str = "http://localhost:8000"
    internal_token: str = "modelforge-internal"
settings = Settings()
```

- [ ] **Step 4: 写依赖**

```python
# services/model-server/server/api_auth.py
import time
import requests
from fastapi import Header, HTTPException
from server.config import settings

_CACHE: dict[tuple[str, str], tuple[bool, float]] = {}
_TTL = 60.0  # seconds


def _remote_verify(key: str, scope: str) -> bool:
    """Ask app-server (single source of truth) whether key has scope."""
    r = requests.post(f"{settings.app_server_url}/internal/api-keys/verify",
                      json={"key": key, "scope": scope},
                      headers={"X-Internal-Token": settings.internal_token}, timeout=5)
    r.raise_for_status()
    return bool(r.json().get("valid"))


def require_api_key(scope: str):
    def dep(x_api_key: str | None = Header(default=None)):
        if not x_api_key:
            raise HTTPException(401, "missing api key")
        cached = _CACHE.get((x_api_key, scope))
        now = time.monotonic()
        if cached and now - cached[1] < _TTL:
            valid = cached[0]
        else:
            try:
                valid = _remote_verify(x_api_key, scope)
            except Exception:
                raise HTTPException(503, "auth backend unavailable")  # fail-closed
            _CACHE[(x_api_key, scope)] = (valid, now)
        if not valid:
            raise HTTPException(401, "invalid or unauthorized api key")
        return None
    return dep
```

- [ ] **Step 5: 跑测试看通过**

Run: `cd services/model-server && python -m pytest tests/test_api_auth.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/model-server/server/config.py services/model-server/server/api_auth.py services/model-server/tests/test_api_auth.py
git commit -m "feat(model-server): X-Api-Key dependency (TTL cache + app-server verify)"
```

---

### Task 2.2: 把鉴权挂到 /predict /embed /similarity

**Files:**
- Modify: `services/model-server/server/main.py`
- Modify: `services/model-server/tests/test_server_api.py`

- [ ] **Step 1: 改现有 server api 测试,让推理调用带 header 并覆盖鉴权**

先看 `tests/test_server_api.py` 怎么调 `/predict` 等;在其 TestClient 调用处加 `headers={"X-Api-Key": "k"}`,并在测试 setup 里 `monkeypatch` 掉 `server.api_auth._remote_verify` 返回 True(或 `server.api_auth.require_api_key` 依赖覆盖)。最简方式:用 FastAPI 依赖覆盖:

```python
# in tests/test_server_api.py setup (wherever the TestClient/app is built)
import server.api_auth as api_auth
monkeypatch.setattr(api_auth, "_remote_verify", lambda key, scope: True)
# and add headers={"X-Api-Key": "k"} to each /predict /embed /similarity call
```

新增一条“无 key 被拒”测试:

```python
def test_predict_requires_api_key(monkeypatch):
    from fastapi.testclient import TestClient
    from server.main import app
    c = TestClient(app)
    r = c.post("/predict", json={"model_version_id": 1, "texts": ["x"]})
    assert r.status_code == 401 and r.json()["code"] == 401
```

- [ ] **Step 2: 跑测试看它失败**

Run: `cd services/model-server && python -m pytest tests/test_server_api.py -q`
Expected: FAIL（401 测试失败,因为现在 /predict 还没鉴权返回 404/200)

- [ ] **Step 3: 给三个端点加依赖**

```python
# services/model-server/server/main.py — import + decorators
from fastapi import Depends
from server.api_auth import require_api_key

# change the three decorators:
@app.post("/predict", dependencies=[Depends(require_api_key("inference"))])
# ...
@app.post("/embed", dependencies=[Depends(require_api_key("inference"))])
# ...
@app.post("/similarity", dependencies=[Depends(require_api_key("inference"))])
```

注:依赖在请求体解析前后顺序——FastAPI 会先跑依赖(含 Header 读取);无 key → 401(走信封 exception handler)。`/load`、`/loaded`、`/health` 不加。

- [ ] **Step 4: 跑测试看通过**

Run: `cd services/model-server && python -m pytest tests/test_server_api.py tests/test_api_auth.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/model-server/server/main.py services/model-server/tests/test_server_api.py
git commit -m "feat(model-server): require X-Api-Key (inference scope) on /predict /embed /similarity"
```

---

### Task 2.3: 部署 API 详情 curl 加 X-Api-Key

**Files:**
- Modify: `frontend/src/apiDocs.ts`

- [ ] **Step 1: 在 curl 生成处加请求头**

查 `frontend/src/apiDocs.ts` 里拼 curl 的地方(`buildApiDoc`),在每个 `-H "Content-Type: application/json"` 旁加一行 `-H "X-Api-Key: <你的 inference key>"`;并在 `reqFields` 或说明文案里注明需要带 `inference` scope 的 API Key(可在「API Key」页创建)。示例:

```ts
// inside the curl template string, add the header line:
//   curl -X POST '<url>' \
//     -H 'Content-Type: application/json' \
//     -H 'X-Api-Key: <your inference key>' \
//     -d '<body>'
```

- [ ] **Step 2: 构建验证**

Run: `cd frontend && npm run build`
Expected: 通过。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/apiDocs.ts
git commit -m "feat(deploy): show X-Api-Key header in inference API docs"
```

---

# Phase 3 — Badcase 上报 + 契约 + 归类列表

### Task 3.1: `Badcase` 模型 + 迁移 013

**Files:**
- Create: `services/app-server/app/models/badcase.py`
- Modify: `services/app-server/app/models/__init__.py`(如需)
- Create: `services/app-server/db/migrations/013_badcases.sql`
- Test: `services/app-server/tests/test_badcase_api.py`

- [ ] **Step 1: 写失败测试(建表 + 字段)**

```python
# services/app-server/tests/test_badcase_api.py
def test_badcase_model_roundtrip(session_factory):
    from app.models.badcase import Badcase
    db = session_factory()
    b = Badcase(model_version_id=1, task_type="classification",
                input={"text": "x"}, inference={"label": "A", "score": 0.9},
                category="A", source="svc", status="reported")
    db.add(b); db.commit(); db.refresh(b)
    assert b.id and b.status == "reported" and b.annotation is None
```

- [ ] **Step 2: 跑测试看它失败**

Run: `cd services/app-server && python -m pytest tests/test_badcase_api.py::test_badcase_model_roundtrip -q`
Expected: FAIL

- [ ] **Step 3: 写模型**

```python
# services/app-server/app/models/badcase.py
from datetime import datetime
from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class Badcase(Base, TimestampMixin):
    __tablename__ = "badcases"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"))
    task_type: Mapped[str] = mapped_column()
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    inference: Mapped[dict] = mapped_column(JSON, default=dict)
    category: Mapped[str | None] = mapped_column(nullable=True)
    source: Mapped[str | None] = mapped_column(nullable=True)
    source_ref: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default="reported")  # reported|annotated|used
    annotation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    annotated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    annotated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    dataset_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_versions.id"), nullable=True)
    model_version: Mapped["ModelVersion | None"] = relationship(  # type: ignore  # noqa: F821
        "ModelVersion", lazy="selectin", foreign_keys=[model_version_id])

    @property
    def model_name(self) -> str | None:
        return self.model_version.name if self.model_version else None

    @property
    def model_version_label(self) -> str | None:
        return self.model_version.mlflow_version if self.model_version else None
```

- [ ] **Step 4: 写迁移 013**

```sql
-- services/app-server/db/migrations/013_badcases.sql
CREATE TABLE IF NOT EXISTS badcases (
    id                  SERIAL PRIMARY KEY,
    model_version_id    INTEGER NOT NULL REFERENCES model_versions(id),
    task_type           TEXT NOT NULL,
    input               JSON NOT NULL DEFAULT '{}',
    inference           JSON NOT NULL DEFAULT '{}',
    category            TEXT,
    source              TEXT,
    source_ref          TEXT,
    status              TEXT NOT NULL DEFAULT 'reported',
    annotation          JSON,
    annotated_by        INTEGER REFERENCES users(id),
    annotated_at        TIMESTAMP,
    dataset_version_id  INTEGER REFERENCES dataset_versions(id),
    created_at          TIMESTAMP DEFAULT now(),
    updated_at          TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_badcases_model_version ON badcases(model_version_id);
CREATE INDEX IF NOT EXISTS ix_badcases_status ON badcases(status);
```

- [ ] **Step 5: 跑测试看通过 + Commit**

Run: `cd services/app-server && python -m pytest tests/test_badcase_api.py::test_badcase_model_roundtrip -q` → PASS

```bash
git add services/app-server/app/models/badcase.py services/app-server/app/models/__init__.py services/app-server/db/migrations/013_badcases.sql services/app-server/tests/test_badcase_api.py
git commit -m "feat(badcase): Badcase model + migration 013"
```

---

### Task 3.2: badcase 契约模块(校验 + 训练行映射 + rules + category)

**Files:**
- Create: `services/app-server/app/badcase_contracts.py`
- Test: `services/app-server/tests/test_badcase_contracts.py`

- [ ] **Step 1: 写失败测试(四类)**

```python
# services/app-server/tests/test_badcase_contracts.py
import pytest
from app import badcase_contracts as bc

def test_validate_input_ok_and_bad():
    bc.validate_input("classification", {"text": "hi"})           # ok
    with pytest.raises(ValueError):
        bc.validate_input("classification", {"foo": "bar"})        # missing text
    bc.validate_input("ner", {"tokens": ["a", "b"]})
    bc.validate_input("pair", {"text_a": "x", "text_b": "y"})
    bc.validate_input("embedding", {"query": "q", "candidates": ["c1", "c2"]})

def test_validate_annotation():
    bc.validate_annotation("classification", {"label": "A"})
    with pytest.raises(ValueError):
        bc.validate_annotation("ner", {"label": "A"})              # needs tags
    bc.validate_annotation("embedding", {"pos": ["c1"], "neg": []})
    with pytest.raises(ValueError):
        bc.validate_annotation("embedding", {"pos": [], "neg": []})  # pos empty

def test_to_training_row():
    assert bc.to_training_row("classification", {"text": "hi"}, {"label": "A"}) == {"text": "hi", "label": "A"}
    assert bc.to_training_row("ner", {"tokens": ["a"]}, {"tags": ["O"]}) == {"tokens": ["a"], "tags": ["O"]}
    assert bc.to_training_row("pair", {"text_a": "x", "text_b": "y"}, {"label": "1"}) == {"text_a": "x", "text_b": "y", "label": "1"}
    assert bc.to_training_row("embedding", {"query": "q", "candidates": ["c1", "c2"]}, {"pos": ["c1"], "neg": ["c2"]}) == {"query": "q", "pos": ["c1"], "neg": ["c2"]}

def test_category_and_rules():
    assert bc.category_of("classification", {"label": "A", "score": 0.9}) == "A"
    assert bc.category_of("ner", {"tags": ["O"]}) is None
    rules = bc.rules()
    assert {r["task_type"] for r in rules} == {"classification", "ner", "pair", "embedding"}
    assert "example" in rules[0]
```

- [ ] **Step 2: 跑测试看它失败**

Run: `cd services/app-server && python -m pytest tests/test_badcase_contracts.py -q`
Expected: FAIL

- [ ] **Step 3: 写契约模块**

```python
# services/app-server/app/badcase_contracts.py
"""Per-task-type badcase contracts: report-input / inference / annotation shapes,
the mapping from an annotated badcase to a training row, and the read-only rules."""

INPUT_KEYS = {
    "classification": ["text"],
    "ner": ["tokens"],
    "pair": ["text_a", "text_b"],
    "embedding": ["query", "candidates"],
}
ANNOTATION_KEYS = {
    "classification": ["label"],
    "ner": ["tags"],
    "pair": ["label"],
    "embedding": ["pos"],   # neg optional
}
TASK_TYPES = list(INPUT_KEYS)


def _require(d: dict, keys: list[str], what: str) -> None:
    if not isinstance(d, dict):
        raise ValueError(f"{what} must be an object")
    missing = [k for k in keys if k not in d or d[k] in (None, "")]
    if missing:
        raise ValueError(f"{what} missing fields: {missing}")


def validate_input(task_type: str, input: dict) -> None:
    if task_type not in INPUT_KEYS:
        raise ValueError(f"unknown task_type: {task_type}")
    _require(input, INPUT_KEYS[task_type], "input")
    if task_type == "embedding" and not input.get("candidates"):
        raise ValueError("input.candidates must be a non-empty list")


def validate_annotation(task_type: str, annotation: dict) -> None:
    if task_type not in ANNOTATION_KEYS:
        raise ValueError(f"unknown task_type: {task_type}")
    _require(annotation, ANNOTATION_KEYS[task_type], "annotation")
    if task_type == "embedding" and not annotation.get("pos"):
        raise ValueError("annotation.pos must be a non-empty list")


def to_training_row(task_type: str, input: dict, annotation: dict) -> dict:
    if task_type == "classification":
        return {"text": input["text"], "label": annotation["label"]}
    if task_type == "ner":
        return {"tokens": input["tokens"], "tags": annotation["tags"]}
    if task_type == "pair":
        return {"text_a": input["text_a"], "text_b": input["text_b"], "label": annotation["label"]}
    if task_type == "embedding":
        return {"query": input["query"], "pos": annotation["pos"], "neg": annotation.get("neg", [])}
    raise ValueError(f"unknown task_type: {task_type}")


def category_of(task_type: str, inference: dict) -> str | None:
    if task_type == "classification" and isinstance(inference, dict):
        return inference.get("label")
    return None


_EXAMPLES = {
    "classification": {"input": {"text": "怎么退货"}, "inference": {"label": "物流查询", "score": 0.82},
                       "annotation": {"label": "售后服务"}},
    "ner": {"input": {"tokens": ["小", "明", "在", "北", "京"]}, "inference": {"tags": ["O", "O", "O", "O", "O"]},
            "annotation": {"tags": ["B-PER", "I-PER", "O", "B-LOC", "I-LOC"]}},
    "pair": {"input": {"text_a": "今天天气如何", "text_b": "明天会下雨吗"}, "inference": {"score": 0.88},
             "annotation": {"label": "0"}},
    "embedding": {"input": {"query": "如何重置密码", "candidates": ["在设置页重置密码", "联系客服热线"]},
                  "inference": {"ranked": [{"text": "联系客服热线", "score": 0.71}, {"text": "在设置页重置密码", "score": 0.63}]},
                  "annotation": {"pos": ["在设置页重置密码"], "neg": ["联系客服热线"]}},
}


def rules() -> list[dict]:
    out = []
    for t in TASK_TYPES:
        out.append({
            "task_type": t,
            "input_keys": INPUT_KEYS[t],
            "annotation_keys": ANNOTATION_KEYS[t] + (["neg(可选)"] if t == "embedding" else []),
            "example": _EXAMPLES[t],
        })
    return out
```

- [ ] **Step 4: 跑测试看通过 + Commit**

Run: `cd services/app-server && python -m pytest tests/test_badcase_contracts.py -q` → PASS

```bash
git add services/app-server/app/badcase_contracts.py services/app-server/tests/test_badcase_contracts.py
git commit -m "feat(badcase): per-task contracts (validate + training-row mapping + rules)"
```

---

### Task 3.3: 上报 service + 上报 API(X-Api-Key)

**Files:**
- Create: `services/app-server/app/api_key_auth.py`
- Create: `services/app-server/app/services/badcase_service.py`
- Create: `services/app-server/app/schemas/badcase.py`
- Create: `services/app-server/app/api/badcase.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_badcase_api.py`(追加)

- [ ] **Step 1: 写失败测试(上报)**

```python
# append to services/app-server/tests/test_badcase_api.py
from fastapi.testclient import TestClient

def _setup_version(session_factory):
    from app import db as dbmod
    db = session_factory()
    from app.models.training import Model, TrainingJob, ModelVersion
    m = Model(name="客服分类", task_type="classification"); db.add(m); db.commit()
    job = TrainingJob(name="j", dataset_version_id=1, base_model="b", task_type="classification", hyperparams={}, model_id=m.id)
    db.add(job); db.commit()
    mv = ModelVersion(name="客服分类", model_id=m.id, source_training_job_id=job.id,
                      mlflow_model_name="客服分类", mlflow_version="1", task_type="classification",
                      base_model="b", train_metrics={})
    db.add(mv); db.commit()
    mvid = mv.id; db.close()
    return mvid

def test_report_badcase_with_api_key(session_factory, monkeypatch):
    mvid = _setup_version(session_factory)
    from app.services import api_key_service
    from app import db as dbmod
    db = dbmod.SessionLocal()
    plaintext, _ = api_key_service.create_key(db, name="svc", scopes=["badcase:report"], created_by=None)
    db.close()
    from app.main import app
    c = TestClient(app)
    # valid report
    r = c.post("/badcase/report", headers={"X-Api-Key": plaintext},
               json={"model_version_id": mvid, "input": {"text": "怎么退货"},
                     "inference": {"label": "物流查询", "score": 0.8}, "source_ref": "ext-1"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "reported" and r.json()["category"] == "物流查询"
    # idempotent on (source, source_ref)
    r2 = c.post("/badcase/report", headers={"X-Api-Key": plaintext},
                json={"model_version_id": mvid, "input": {"text": "怎么退货"},
                      "inference": {"label": "物流查询"}, "source_ref": "ext-1"})
    assert r2.json()["id"] == r.json()["id"]
    # bad input -> 422
    assert c.post("/badcase/report", headers={"X-Api-Key": plaintext},
                  json={"model_version_id": mvid, "input": {"nope": 1}, "inference": {}}).status_code == 422
    # missing/invalid key -> 401
    assert c.post("/badcase/report", json={"model_version_id": mvid, "input": {"text": "x"}, "inference": {}}).status_code == 401
    # unknown version -> 422
    assert c.post("/badcase/report", headers={"X-Api-Key": plaintext},
                  json={"model_version_id": 99999, "input": {"text": "x"}, "inference": {}}).status_code == 422
```

- [ ] **Step 2: 跑测试看它失败**

Run: `cd services/app-server && python -m pytest tests/test_badcase_api.py -k report -q`
Expected: FAIL

- [ ] **Step 3: X-Api-Key 依赖(app-server 进程内校验)**

```python
# services/app-server/app/api_key_auth.py
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.services import api_key_service
from app.models.api_key import ApiKey


def require_api_key(scope: str):
    def dep(x_api_key: str | None = Header(default=None),
            db: Session = Depends(get_db)) -> ApiKey:
        key = api_key_service.verify(db, x_api_key or "", scope)
        if not key:
            raise HTTPException(401, "missing or invalid api key")
        return key
    return dep
```

- [ ] **Step 4: schemas + service + API**

```python
# services/app-server/app/schemas/badcase.py
from datetime import datetime
from pydantic import BaseModel

class BadcaseReportIn(BaseModel):
    model_version_id: int
    input: dict
    inference: dict = {}
    source_ref: str | None = None

class BadcaseAnnotateIn(BaseModel):
    annotation: dict

class BuildDatasetIn(BaseModel):
    badcase_ids: list[int]
    name: str | None = None

class BadcaseOut(BaseModel):
    id: int
    model_version_id: int
    model_name: str | None = None
    model_version_label: str | None = None
    task_type: str
    input: dict
    inference: dict
    category: str | None
    source: str | None
    source_ref: str | None
    status: str
    annotation: dict | None
    dataset_version_id: int | None
    created_at: datetime
    class Config: from_attributes = True
```

```python
# services/app-server/app/services/badcase_service.py
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import badcase_contracts as bc
from app.models.badcase import Badcase
from app.models.training import ModelVersion
from app.models.dataset import Dataset
from app.services.dataset_service import create_version
from app.storage import build_storage


def report(db: Session, body, source: str | None) -> Badcase:
    mv = db.get(ModelVersion, body.model_version_id)
    if not mv:
        raise ValueError("model_version not found")
    bc.validate_input(mv.task_type, body.input)
    if body.source_ref:  # idempotent dedup on (source, source_ref)
        existing = db.execute(select(Badcase).where(
            Badcase.source == source, Badcase.source_ref == body.source_ref)).scalar_one_or_none()
        if existing:
            return existing
    case = Badcase(model_version_id=mv.id, task_type=mv.task_type, input=body.input,
                   inference=body.inference or {}, category=bc.category_of(mv.task_type, body.inference or {}),
                   source=source, source_ref=body.source_ref, status="reported")
    db.add(case); db.commit(); db.refresh(case)
    return case


def annotate(db: Session, case_id: int, annotation: dict, user_id: int) -> Badcase:
    case = db.get(Badcase, case_id)
    if not case:
        raise ValueError("badcase not found")
    bc.validate_annotation(case.task_type, annotation)
    case.annotation = annotation
    case.status = "annotated"
    case.annotated_by = user_id
    case.annotated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(case)
    return case


def build_dataset(db: Session, badcase_ids: list[int], name: str | None, user_id: int):
    import pandas as pd
    if not badcase_ids:
        raise ValueError("badcase_ids required")
    cases = list(db.execute(select(Badcase).where(Badcase.id.in_(badcase_ids))).scalars())
    if len(cases) != len(set(badcase_ids)):
        raise ValueError("some badcases not found")
    task_types = {c.task_type for c in cases}
    if len(task_types) != 1:
        raise ValueError("badcases must share one task_type")
    if any(c.status != "annotated" and c.annotation is None for c in cases):
        raise ValueError("all badcases must be annotated first")
    task_type = task_types.pop()
    rows = [bc.to_training_row(task_type, c.input, c.annotation) for c in cases]
    df = pd.DataFrame(rows)

    ds_name = name or f"badcase-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    if not ds_name.startswith("badcase-"):
        ds_name = "badcase-" + ds_name
    ds = Dataset(name=ds_name, kind="train", task_type=task_type, created_by=user_id)
    db.add(ds); db.commit(); db.refresh(ds)
    version = create_version(db, build_storage(), ds, df, note="from badcases", created_by=user_id)
    for c in cases:
        c.status = "used"
        c.dataset_version_id = version.id
    db.commit()
    return ds, version
```

```python
# services/app-server/app/api/badcase.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.api_key_auth import require_api_key
from app.models.user import User
from app.models.api_key import ApiKey
from app.models.badcase import Badcase
from app import badcase_contracts as bc
from app.schemas.badcase import BadcaseReportIn, BadcaseAnnotateIn, BuildDatasetIn, BadcaseOut
from app.services import badcase_service

router = APIRouter(tags=["badcase"])


@router.post("/badcase/report", response_model=BadcaseOut, status_code=201)
def report(body: BadcaseReportIn, key: ApiKey = Depends(require_api_key("badcase:report")),
           db: Session = Depends(get_db)):
    try:
        return badcase_service.report(db, body, source=key.name)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/badcase/rules")
def rules(_: User = Depends(require("badcase:read"))):
    return {"rules": bc.rules()}


@router.get("/badcases", response_model=list[BadcaseOut])
def list_badcases(model_version_id: int | None = None, status: str | None = None,
                  category: str | None = None, _: User = Depends(require("badcase:read")),
                  db: Session = Depends(get_db)):
    q = select(Badcase).order_by(Badcase.id.desc())
    if model_version_id is not None:
        q = q.where(Badcase.model_version_id == model_version_id)
    if status:
        q = q.where(Badcase.status == status)
    if category:
        q = q.where(Badcase.category == category)
    return list(db.execute(q).scalars())


@router.get("/badcases/{case_id}", response_model=BadcaseOut)
def get_badcase(case_id: int, _: User = Depends(require("badcase:read")),
                db: Session = Depends(get_db)):
    case = db.get(Badcase, case_id)
    if not case:
        raise HTTPException(404, "not found")
    return case


@router.patch("/badcases/{case_id}/annotate", response_model=BadcaseOut)
def annotate(case_id: int, body: BadcaseAnnotateIn, user: User = Depends(require("badcase:annotate")),
             db: Session = Depends(get_db)):
    try:
        return badcase_service.annotate(db, case_id, body.annotation, user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/badcases/build-dataset", status_code=201)
def build_dataset(body: BuildDatasetIn, user: User = Depends(require("dataset:write")),
                  db: Session = Depends(get_db)):
    try:
        ds, version = badcase_service.build_dataset(db, body.badcase_ids, body.name, user.id)
        return {"dataset_id": ds.id, "dataset_name": ds.name,
                "version_id": version.id, "version_no": version.version_no, "row_count": version.row_count}
    except ValueError as e:
        raise HTTPException(422, str(e))
```

```python
# services/app-server/app/main.py — register
from app.api import badcase
app.include_router(badcase.router)
```

- [ ] **Step 5: 跑测试看通过 + Commit**

Run: `cd services/app-server && python -m pytest tests/test_badcase_api.py -q` → PASS

```bash
git add services/app-server/app/api_key_auth.py services/app-server/app/services/badcase_service.py services/app-server/app/schemas/badcase.py services/app-server/app/api/badcase.py services/app-server/app/main.py services/app-server/tests/test_badcase_api.py
git commit -m "feat(badcase): report API (X-Api-Key) + rules/list/detail endpoints"
```

---

### Task 3.4: `badcase:read` / `badcase:annotate` 权限 + 迁移 014 + bootstrap

**Files:**
- Modify: `services/app-server/app/bootstrap.py`
- Create: `services/app-server/db/migrations/014_badcase_perms.sql`
- Test: `services/app-server/tests/test_bootstrap.py`

- [ ] **Step 1: 更新计数 + 新断言**

把权限总数断言再 +2(`badcase:read`、`badcase:annotate`)。新增:

```python
def test_badcase_perms_seeded(session_factory):
    from app.bootstrap import seed
    from app.models.rbac import Permission, Role
    from sqlalchemy import select
    db = session_factory(); seed(db)
    codes = {p.code for p in db.execute(select(Permission)).scalars()}
    assert {"badcase:read", "badcase:annotate"} <= codes
    member = db.execute(select(Role).where(Role.name == "member")).scalar_one()
    mp = {p.code for p in member.permissions}
    assert "badcase:read" in mp and "badcase:annotate" in mp
    viewer = db.execute(select(Role).where(Role.name == "viewer")).scalar_one()
    assert "badcase:read" in {p.code for p in viewer.permissions} and "badcase:annotate" not in {p.code for p in viewer.permissions}
```

- [ ] **Step 2: 跑测试看它失败**

Run: `cd services/app-server && python -m pytest tests/test_bootstrap.py -q` → FAIL

- [ ] **Step 3: 改 bootstrap**

```python
# services/app-server/app/bootstrap.py — extend catalog + role grants
PERMISSION_CATALOG = [
    # ... existing entries ...
    ("apikey:manage", "API Key 管理"),
    ("badcase:read", "看 Badcase / 上报规则"),
    ("badcase:annotate", "标注 Badcase"),
    ("*", "通配"),
]
READS = ["dataset:read", "training:read", "model:read", "eval:read", "deploy:read", "badcase:read"]
BUSINESS = READS + ["dataset:write", "training:run", "eval:run", "deploy:write", "model:write", "badcase:annotate"]
ADMIN_PERMS = BUSINESS + ["apikey:manage"]
```

(`viewer` = READS → 含 `badcase:read`,不含 annotate;`member`/`admin` = BUSINESS → 含两者。)

- [ ] **Step 4: 迁移 014**

```sql
-- services/app-server/db/migrations/014_badcase_perms.sql
INSERT INTO permissions (code, description) VALUES
  ('badcase:read', '看 Badcase / 上报规则'),
  ('badcase:annotate', '标注 Badcase')
ON CONFLICT (code) DO NOTHING;

-- badcase:read -> admin, member, viewer
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member', 'viewer') AND p.code = 'badcase:read'
ON CONFLICT DO NOTHING;

-- badcase:annotate -> admin, member
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member') AND p.code = 'badcase:annotate'
ON CONFLICT DO NOTHING;
```

- [ ] **Step 5: 跑测试看通过 + Commit**

Run: `cd services/app-server && python -m pytest tests/test_bootstrap.py -q` → PASS

```bash
git add services/app-server/app/bootstrap.py services/app-server/db/migrations/014_badcase_perms.sql services/app-server/tests/test_bootstrap.py
git commit -m "feat(badcase): badcase:read/annotate permissions + migration 014"
```

---

### Task 3.5: 前端 Badcase 列表(按模型版本归类)+ 规则页 + 导航

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/BadcasePage.tsx`、`frontend/src/pages/BadcaseRulesPage.tsx`
- Modify: `frontend/src/components/AppShell.tsx`、`frontend/src/App.tsx`

- [ ] **Step 1: 客户端类型/函数**

```ts
// frontend/src/api/client.ts — append
export type Badcase = { id: number; model_version_id: number; model_name: string | null; model_version_label: string | null; task_type: string; input: Record<string, any>; inference: Record<string, any>; category: string | null; source: string | null; source_ref: string | null; status: string; annotation: Record<string, any> | null; dataset_version_id: number | null; created_at: string };
export const listBadcases = (p?: { model_version_id?: number; status?: string; category?: string }) =>
  api.get<Badcase[]>("/badcases", { params: p ?? {} }).then(r => r.data);
export const getBadcase = (id: number) => api.get<Badcase>(`/badcases/${id}`).then(r => r.data);
export const annotateBadcase = (id: number, annotation: Record<string, any>) =>
  api.patch<Badcase>(`/badcases/${id}/annotate`, { annotation }).then(r => r.data);
export const buildBadcaseDataset = (badcase_ids: number[], name?: string) =>
  api.post<{ dataset_id: number; dataset_name: string; version_id: number; version_no: number; row_count: number }>("/badcases/build-dataset", { badcase_ids, name }).then(r => r.data);
export const listBadcaseRules = () => api.get<{ rules: any[] }>("/badcase/rules").then(r => r.data.rules);
```

- [ ] **Step 2: 规则页(只读契约 + 示例 + 上报 curl)**

```tsx
// frontend/src/pages/BadcaseRulesPage.tsx
import { useEffect, useState } from "react";
import { listBadcaseRules } from "../api/client";
import { PageHeader, Badge, Card } from "../ui";
import { toastError } from "../toast";

const TASK_LABEL: Record<string, string> = { classification: "分类", ner: "序列标注", pair: "句对", embedding: "向量检索" };

export function BadcaseRulesPage() {
  const [rules, setRules] = useState<any[]>([]);
  useEffect(() => { listBadcaseRules().then(setRules).catch(() => toastError("加载失败")); }, []);
  return (
    <>
      <PageHeader title="上报规则" subtitle="每种模型类型的 Badcase 上报契约;外部业务用带 badcase:report 的 API Key 调用 POST /badcase/report。" />
      <div className="flex flex-col gap-4">
        {rules.map(r => (
          <Card key={r.task_type} className="p-5">
            <div className="mb-3 flex items-center gap-2"><Badge tone="blue">{TASK_LABEL[r.task_type] ?? r.task_type}</Badge>
              <span className="font-mono text-[12px] text-slate-500">{r.task_type}</span></div>
            <div className="grid grid-cols-2 gap-4 text-[12.5px]">
              <div><div className="label mb-1">input 字段</div><div className="font-mono text-slate-600">{r.input_keys.join(", ")}</div></div>
              <div><div className="label mb-1">annotation 字段(系统内标注)</div><div className="font-mono text-slate-600">{r.annotation_keys.join(", ")}</div></div>
            </div>
            <div className="mt-3"><div className="label mb-1">上报示例</div>
              <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 font-mono text-[11.5px] text-slate-100">{`curl -X POST '$API/badcase/report' \\
  -H 'Content-Type: application/json' \\
  -H 'X-Api-Key: <badcase:report key>' \\
  -d '${JSON.stringify({ model_version_id: 1, input: r.example.input, inference: r.example.inference })}'`}</pre>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
```

（若 `Card` 未从 `ui` 导出,改用现成容器 `<div className="rounded-xl border border-slate-200 bg-white p-5">`。）

- [ ] **Step 3: Badcase 列表页(按 模型→版本 分组 + 状态筛选 + 多选 + 生成训练集 + 去修复 入口)**

```tsx
// frontend/src/pages/BadcasePage.tsx
import { useEffect, useMemo, useState } from "react";
import { Bug, FlaskConical, Database } from "lucide-react";
import { listBadcases, buildBadcaseDataset, type Badcase } from "../api/client";
import { Badge, Button, EmptyState, PageHeader, Select, StatusBadge, TableShell } from "../ui";
import { toastError, toastSuccess } from "../toast";
import { navigate } from "../router";
import { BadcaseAnnotateDrawer } from "./BadcaseAnnotateDrawer"; // created in Task 4.3

const STATUS = [{ v: "", l: "全部状态" }, { v: "reported", l: "待标注" }, { v: "annotated", l: "已标注" }, { v: "used", l: "已用" }];

export function BadcasePage() {
  const [items, setItems] = useState<Badcase[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [sel, setSel] = useState<number[]>([]);
  const [anno, setAnno] = useState<Badcase | null>(null);
  const [busy, setBusy] = useState(false);
  const reload = () => listBadcases(status ? { status } : undefined).then(setItems);
  useEffect(() => { reload().finally(() => setLoading(false)); }, [status]);

  // auto-group by model -> version
  const groups = useMemo(() => {
    const m = new Map<string, Badcase[]>();
    for (const b of items) {
      const k = `${b.model_name ?? b.model_version_id} · V${b.model_version_label ?? "?"}`;
      (m.get(k) ?? m.set(k, []).get(k)!).push(b);
    }
    return [...m.entries()];
  }, [items]);

  const toggle = (id: number) => setSel(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);
  const selected = items.filter(b => sel.includes(b.id));
  const canBuild = selected.length > 0 && selected.every(b => b.status === "annotated" || b.annotation) &&
    new Set(selected.map(b => b.task_type)).size === 1;

  const build = () => {
    setBusy(true);
    buildBadcaseDataset(sel).then(res => {
      toastSuccess(`已生成训练集 ${res.dataset_name}(${res.row_count} 行)`);
      setSel([]); reload();
      // 去修复:跳到训练页并预选(训练页读取 query 参数,见 Task 5.1)
      navigate(`/training?badcase_version=${res.version_id}`);
    }).catch(() => toastError("生成失败(需都已标注且同一类型)")).finally(() => setBusy(false));
  };

  return (
    <>
      <PageHeader title="Badcase" subtitle="外部上报的坏例按模型版本自动归类;标注后可一键生成 badcase- 训练集并去修复。"
        actions={<Button variant="primary" disabled={!canBuild} loading={busy} onClick={build}><Database size={16} /> 生成训练集并去修复 ({sel.length})</Button>} />
      <div className="mb-4 flex items-center gap-2.5">
        <span className="text-[13px] text-slate-500">状态</span>
        <Select className="h-9 w-40" value={status} onChange={e => setStatus(e.target.value)}>
          {STATUS.map(s => <option key={s.v} value={s.v}>{s.l}</option>)}
        </Select>
      </div>

      {loading ? <TableShell loading head={<th>加载中</th>}>{null}</TableShell> :
        items.length === 0 ? <EmptyState icon={<Bug size={22} />} title="还没有 Badcase" hint="外部业务通过 API 上报后会自动出现在这里。" /> :
        groups.map(([title, rows]) => (
          <div key={title} className="mb-5">
            <div className="mb-2 flex items-center gap-2 text-[14px] font-medium text-slate-800"><Bug size={15} className="text-slate-400" /> {title} <span className="text-slate-400">({rows.length})</span></div>
            <TableShell head={<><th className="w-10"></th><th className="w-14">#</th><th>输入</th><th>模型推理</th><th>状态</th><th>标注</th><th className="w-28 text-right"></th></>}>
              {rows.map(b => (
                <tr key={b.id}>
                  <td><input type="checkbox" className="accent-brand-500" checked={sel.includes(b.id)} onChange={() => toggle(b.id)} /></td>
                  <td className="font-mono text-slate-400">{b.id}</td>
                  <td className="max-w-xs truncate text-slate-700">{JSON.stringify(b.input)}</td>
                  <td className="max-w-xs truncate text-slate-500">{JSON.stringify(b.inference)}</td>
                  <td><StatusBadge status={b.status} /></td>
                  <td className="max-w-[160px] truncate text-slate-500">{b.annotation ? JSON.stringify(b.annotation) : <span className="text-slate-300">—</span>}</td>
                  <td className="text-right"><Button size="sm" onClick={() => setAnno(b)}><FlaskConical size={13} /> 标注</Button></td>
                </tr>
              ))}
            </TableShell>
          </div>
        ))}

      <BadcaseAnnotateDrawer badcase={anno} onClose={() => setAnno(null)} onSaved={() => { setAnno(null); reload(); }} />
    </>
  );
}
```

- [ ] **Step 4: 导航 + 路由(Badcase + 上报规则)**

```tsx
// frontend/src/components/AppShell.tsx — import Bug, BookText; add to NAV (after 测试/部署):
{ href: "/badcase", label: "Badcase", icon: <Bug size={18} />, perm: "badcase:read", match: p => p.startsWith("/badcase") && !p.startsWith("/badcase-rules") },
{ href: "/badcase-rules", label: "上报规则", icon: <BookText size={18} />, perm: "badcase:read", match: p => p.startsWith("/badcase-rules") },
```

```tsx
// frontend/src/App.tsx
import { BadcasePage } from "./pages/BadcasePage";
import { BadcaseRulesPage } from "./pages/BadcaseRulesPage";
// routes:
else if (path === "/badcase-rules") page = <BadcaseRulesPage />;
else if (path.startsWith("/badcase")) page = <BadcasePage />;
```

- [ ] **Step 5: 构建验证(此时 BadcaseAnnotateDrawer 尚未建,会失败——下一阶段补)**

把 Step 5 留到 Task 4.3 之后整体 `npm run build`。本任务先 Commit 后端可用部分;前端在 4.3 一起通过构建。

```bash
git add frontend/src/api/client.ts frontend/src/pages/BadcasePage.tsx frontend/src/pages/BadcaseRulesPage.tsx frontend/src/components/AppShell.tsx frontend/src/App.tsx
git commit -m "feat(badcase): list page (grouped by model version) + rules page + nav"
```

---

# Phase 4 — 标注 + 生成训练集

### Task 4.1: build-dataset 后端测试(四类映射 + 边界)

> 后端 annotate / build-dataset 已在 Task 3.3 实现;本任务补足**测试覆盖**(TDD 补测),并修任何暴露的 bug。

**Files:**
- Create: `services/app-server/tests/test_badcase_build_dataset.py`

- [ ] **Step 1: 写测试**

```python
# services/app-server/tests/test_badcase_build_dataset.py
from fastapi.testclient import TestClient

def test_annotate_and_build_dataset(session_factory, monkeypatch):
    # reuse helpers from test_badcase_api
    from tests.test_badcase_api import _setup_version
    mvid = _setup_version(session_factory)
    from app import db as dbmod
    from app.models.badcase import Badcase
    db = dbmod.SessionLocal()
    for t in ["怎么退货", "在哪开发票"]:
        db.add(Badcase(model_version_id=mvid, task_type="classification",
                       input={"text": t}, inference={"label": "物流查询"}, status="reported"))
    db.commit()
    ids = [b.id for b in db.execute(__import__("sqlalchemy").select(Badcase)).scalars()]
    db.close()

    from tests.conftest import make_user, auth_headers
    d = dbmod.SessionLocal(); u = make_user(d, codes=("*",), data_scope="all", email="bc@x.com"); d.close()
    H = auth_headers(u.id)
    # stub storage so no real MinIO needed
    import app.services.badcase_service as bs
    class _Store:
        def write_snapshot(self, dataset_id, version_no, df):
            return (f"s3://x/{dataset_id}/v{version_no}", "sum", len(df))
    monkeypatch.setattr(bs, "build_storage", lambda: _Store())

    from app.main import app
    c = TestClient(app)
    # build before annotate -> 422
    assert c.post("/badcases/build-dataset", json={"badcase_ids": ids}, headers=H).status_code == 422
    # annotate both
    for i in ids:
        assert c.patch(f"/badcases/{i}/annotate", json={"annotation": {"label": "售后服务"}}, headers=H).status_code == 200
    # build -> creates badcase- dataset
    r = c.post("/badcases/build-dataset", json={"badcase_ids": ids}, headers=H)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["dataset_name"].startswith("badcase-") and body["row_count"] == 2
    # cases now used
    assert c.get(f"/badcases/{ids[0]}", headers=H).json()["status"] == "used"
```

- [ ] **Step 2: 跑测试**

Run: `cd services/app-server && python -m pytest tests/test_badcase_build_dataset.py -q`
Expected: PASS（若失败,按报错修 `badcase_service.build_dataset`/`dataset_service.create_version` 的对接;注意 `create_version` 会调 `validate_rows`,分类行 `{text,label}` 合法)。

- [ ] **Step 3: Commit**

```bash
git add services/app-server/tests/test_badcase_build_dataset.py
git commit -m "test(badcase): annotate + build-dataset (classification) coverage"
```

---

### Task 4.2: 标注抽屉组件(按 task_type 渲染)

**Files:**
- Create: `frontend/src/pages/BadcaseAnnotateDrawer.tsx`

- [ ] **Step 1: 写组件**

```tsx
// frontend/src/pages/BadcaseAnnotateDrawer.tsx
import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { annotateBadcase, type Badcase } from "../api/client";
import { Button, Drawer, Field, Input } from "../ui";
import { toastError, toastSuccess } from "../toast";

export function BadcaseAnnotateDrawer({ badcase, onClose, onSaved }: {
  badcase: Badcase | null; onClose: () => void; onSaved: () => void;
}) {
  const [val, setVal] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { setVal(badcase?.annotation ?? {}); }, [badcase]);
  if (!badcase) return null;
  const t = badcase.task_type;

  // build annotation payload per task type
  const set = (k: string, v: any) => setVal(s => ({ ...s, [k]: v }));
  const candidates: string[] = badcase.input?.candidates ?? [];

  const valid = (
    (t === "classification" && val.label) ||
    (t === "pair" && (val.label === "0" || val.label === "1")) ||
    (t === "ner" && Array.isArray(val.tags) && val.tags.length) ||
    (t === "embedding" && Array.isArray(val.pos) && val.pos.length)
  );

  const save = () => {
    setBusy(true);
    annotateBadcase(badcase.id, val).then(() => { toastSuccess("已标注"); onSaved(); })
      .catch(() => toastError("标注失败")).finally(() => setBusy(false));
  };

  return (
    <Drawer open onClose={onClose} title={`标注 Badcase #${badcase.id}`}
      subtitle="补充正确答案;标注后可被选入 badcase- 训练集。"
      footer={<div className="flex items-center justify-end gap-2">
        <Button variant="subtle" disabled={busy} onClick={onClose}>取消</Button>
        <Button variant="primary" disabled={!valid} loading={busy} onClick={save}><Check size={16} /> 保存标注</Button>
      </div>}>
      <div className="flex flex-col gap-4">
        <Field label="模型输入"><pre className="rounded-lg bg-slate-50 p-2 font-mono text-[12px] text-slate-600">{JSON.stringify(badcase.input, null, 2)}</pre></Field>
        <Field label="模型推理(错误)"><pre className="rounded-lg bg-slate-50 p-2 font-mono text-[12px] text-slate-500">{JSON.stringify(badcase.inference, null, 2)}</pre></Field>

        {t === "classification" && <Field label="正确标签 label"><Input value={val.label ?? ""} onChange={e => set("label", e.target.value)} placeholder="如 售后服务" /></Field>}
        {t === "pair" && <Field label="正确标签(1=相似 / 0=不相似)"><Input value={val.label ?? ""} onChange={e => set("label", e.target.value.trim())} placeholder="0 或 1" /></Field>}
        {t === "ner" && <Field label="正确 tags(逗号分隔,与 tokens 等长)">
          <Input value={(val.tags ?? []).join(",")} onChange={e => set("tags", e.target.value.split(",").map(x => x.trim()).filter(Boolean))} placeholder="B-PER,I-PER,O,B-LOC,I-LOC" />
        </Field>}
        {t === "embedding" && (
          <Field label="逐个标注候选(pos=相关 / neg=不相关)">
            <div className="flex flex-col gap-1.5">
              {candidates.map(c => {
                const inPos = (val.pos ?? []).includes(c), inNeg = (val.neg ?? []).includes(c);
                const mark = (key: "pos" | "neg") => {
                  const other = key === "pos" ? "neg" : "pos";
                  set(key, [...new Set([...(val[key] ?? []), c])]);
                  set(other, (val[other] ?? []).filter((x: string) => x !== c));
                };
                return (
                  <div key={c} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2">
                    <span className="flex-1 truncate text-[13px] text-slate-700">{c}</span>
                    <Button size="sm" variant={inPos ? "primary" : "subtle"} onClick={() => mark("pos")}>相关</Button>
                    <Button size="sm" variant={inNeg ? "danger" : "subtle"} onClick={() => mark("neg")}>不相关</Button>
                  </div>
                );
              })}
            </div>
          </Field>
        )}
      </div>
    </Drawer>
  );
}
```

- [ ] **Step 2: 构建验证(现在前端整体应能通过)**

Run: `cd frontend && npm run build`
Expected: 通过(BadcasePage 引用的 Drawer 现已存在)。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/BadcaseAnnotateDrawer.tsx
git commit -m "feat(badcase): task-aware annotation drawer"
```

---

# Phase 5 — 修复联动 + 收尾

### Task 5.1: 训练页支持从 Badcase 预选数据集(去修复)

**Files:**
- Modify: `frontend/src/pages/TrainingPage.tsx`

- [ ] **Step 1: 读取 query 参数预选训练集并自动打开抽屉**

在 `TrainingPage` 的初始 `useEffect` 里读取 `badcase_version`:若存在,自动打开新建训练抽屉,并把该 version 预置到 `dvIds`(训练集多选)。由于该 version 属于刚建的 `badcase-` 训练集,`listDatasetTree("train")` 会包含它。实现:

```tsx
// in TrainingPage(), after existing effects:
useEffect(() => {
  const params = new URLSearchParams(window.location.search);
  const v = params.get("badcase_version");
  if (v) {
    setOpen(true);
    setDvIds([v]);  // preselect the badcase train-set version
    // model: leave for user to pick (default could be the badcase model); clear query
    window.history.replaceState({}, "", "/training");
  }
}, []);
```

注:用户仍需在抽屉里选「模型」(默认让用户选 badcase 所属模型);训练集已预选该 badcase 集,可再多选原训练集合并(复用已实现的多选合并)。

- [ ] **Step 2: 构建验证**

Run: `cd frontend && npm run build`
Expected: 通过。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/TrainingPage.tsx
git commit -m "feat(badcase): 'go repair' — training drawer preselects the badcase dataset"
```

---

### Task 5.2: 全量回归 + 迁移落库 + 服务重启验证

**Files:** 无新代码(验证 + 可能修小问题)。

- [ ] **Step 1: app-server 全量测试**

Run: `cd services/app-server && python -m pytest -q`
Expected: 全绿(含新增 api-key / badcase / contracts / build-dataset / bootstrap 测试)。

- [ ] **Step 2: model-server 测试**

Run: `cd services/model-server && python -m pytest -q`
Expected: 全绿。

- [ ] **Step 3: 前端构建**

Run: `cd frontend && npm run build`
Expected: 通过。

- [ ] **Step 4: 迁移落 PG + 服务重启**

重启 app-server(自动应用 011–014),确认列存在:

```bash
cd services/app-server && python - <<'PY'
from app.config import settings
from sqlalchemy import create_engine, text
e = create_engine(settings.database_url)
with e.connect() as c:
    for tbl in ("api_keys", "badcases"):
        n = c.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_name=:t"), {"t": tbl}).scalar()
        print(tbl, "exists:", n == 1)
    perms = [r[0] for r in c.execute(text("SELECT code FROM permissions WHERE code LIKE 'badcase%' OR code='apikey:manage'"))]
    print("new perms:", sorted(perms))
PY
```

Expected: `api_keys exists: True`、`badcases exists: True`、`new perms: ['apikey:manage', 'badcase:annotate', 'badcase:read']`。

- [ ] **Step 5: 手动冒烟(可选)**

启动三服务 + 前端:创建一个 `inference`+`badcase:report` 的 API Key → 用它调一次 model-server `/predict`(带 `X-Api-Key`,200)→ 调 `/badcase/report` 上报一条分类 badcase → Badcase 页按模型版本归类可见 → 标注 → 生成 `badcase-` 训练集 → 跳训练页预选 → 选模型提交训练 → 出新版本。

- [ ] **Step 6: Commit(若有修)**

```bash
git add -A && git commit -m "chore(badcase): regression fixes + verify migrations applied"
```

---

## Self-Review(执行者无需做,作者已核对)

- **Spec 覆盖**:API Key 体系(§4)→ P1;model-server 推理鉴权(§4.4)→ P2;上报契约/规则(§6)→ Task 3.2/3.4;上报 API(§7)→ Task 3.3;归类列表(§3/§11)→ Task 3.5;标注 + 生成训练集(§8)→ Task 3.3/4.1/4.2;修复(§9)→ Task 5.1;RBAC/迁移(§10/§12)→ Task 1.3/3.4;边界(§13)→ 各 Task 测试;测试(§14)→ 各 Task。embedding 全流程含 Task 3.2/4.2。
- **类型一致**:`api_key_service.create_key`→`(plaintext, ApiKey)`、`verify(db,key,scope)`、`require_api_key(scope)`(app-server 与 model-server 同名不同实现,前者进程内、后者远程缓存,已分别命名于 `app/api_key_auth.py` 与 `server/api_auth.py`)、`badcase_contracts.{validate_input,validate_annotation,to_training_row,category_of,rules}`、`badcase_service.{report,annotate,build_dataset}` 在各 Task 一致。
- **无占位符**:每个改代码的 Step 均给出完整代码与可执行命令。

## 执行选择

Plan complete and saved to `docs/superpowers/plans/2026-06-14-badcase-reporting.md`. 两种执行方式:
1. **Subagent-Driven(推荐)** — 每个 Task 派新 subagent,任务间两段评审(spec 符合 → 代码质量),快速迭代。
2. **Inline 执行** — 本会话内按 executing-plans 分批执行,带检查点。
