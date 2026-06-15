# 子项目 B:Prompt 管理 + Prompt 测试集 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户管理带 `{{参数}}` 模板的 Prompt(system+user,不可变版本)并维护 Prompt 测试集(复用数据集表,列即参数),为后续评测(C/D)提供素材。

**Architecture:** app-server 新增 `prompts`/`prompt_versions` 两表 + `/prompts` API;`{{name}}` 抽参/校验抽到 `services/common` 的 `prompt_template`(C 复用);Prompt 测试集复用 `datasets`/`dataset_versions`,新增 `DatasetKind.PROMPT`,`create_version` 按 kind 分支跳过固定列校验(列名照旧写进 `stats.columns`)。前端加 Prompt 页 + 数据集页 prompt 类型。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + 编号 SQL 迁移;pandas;pytest;React 19 + Vite + TS + Tailwind v4。

**Spec:** [`docs/superpowers/specs/2026-06-15-prompt-eval-B-prompts-and-prompt-datasets-design.md`](../specs/2026-06-15-prompt-eval-B-prompts-and-prompt-datasets-design.md)

**铁律(`CLAUDE.md`)**:改 `app/models/**` 必配【下一个编号】幂等 `db/migrations/NNN_*.sql`;改 RBAC 目录时 `bootstrap.py` 与编号迁移两处一起改。当前最新迁移 = `018_llm_manage_perm.sql`,本计划新增 `019`、`020`。提交信息都以 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` 结尾。

## 文件结构

| 文件 | 职责 | 任务 |
|---|---|---|
| `services/common/modelforge_common/prompt_template.py` | `{{name}}` 抽参 + 语法校验 | T1 |
| `services/common/tests/test_prompt_template.py` | 模板工具单测 | T1 |
| `services/app-server/app/models/prompt.py` | `Prompt`/`PromptVersion` 模型 + latest 属性 | T2 |
| `services/app-server/app/models/__init__.py` | 注册模型 | T2 |
| `services/app-server/db/migrations/019_prompts.sql` | 建两表 | T2 |
| `services/app-server/app/bootstrap.py` | `prompt:read`/`prompt:write` | T3 |
| `services/app-server/db/migrations/020_prompt_perms.sql` | 权限种子 | T3 |
| `services/app-server/tests/test_bootstrap.py`、`tests/test_migrations_apply.py` | 计数断言 +2 表 +2 权限 | T3 |
| `services/common/modelforge_common/enums.py` | `DatasetKind.PROMPT` | T4 |
| `services/app-server/app/services/dataset_service.py` | prompt 分支(跳过固定列校验) | T4 |
| `services/app-server/app/schemas/prompt.py` | Prompt + PromptDataset schema | T5 |
| `services/app-server/app/services/prompt_service.py` | create/add_version/validate | T6 |
| `services/app-server/app/api/prompt.py` | `/prompts` 路由 | T7 |
| `services/app-server/app/api/datasets.py` | `POST /datasets/prompt` | T7 |
| `services/app-server/app/main.py` | 注册 prompt 路由 | T7 |
| `services/app-server/tests/test_prompts.py` | 模型/service/API/数据集分支 测试 | T2,T4,T6,T7 |
| `frontend/src/api/client.ts` | prompt client + createPromptDataset | T8 |
| `frontend/src/pages/PromptsPage.tsx` | Prompt 页 | T9 |
| `frontend/src/App.tsx`、`components/AppShell.tsx` | 路由 + 导航 | T9 |
| `frontend/src/pages/DatasetsPage.tsx` | prompt 类型集成 | T10 |

---

### Task 1: 共享模板工具 `prompt_template`

**Files:**
- Create: `services/common/modelforge_common/prompt_template.py`
- Test: `services/common/tests/test_prompt_template.py`

- [ ] **Step 1: 写失败测试**

`services/common/tests/test_prompt_template.py`:

```python
from modelforge_common.prompt_template import extract_params, validate_template


def test_extract_basic_order():
    assert extract_params("你好 {{ name }},来自 {{ city }}") == ["name", "city"]


def test_extract_dedup_chinese_no_space():
    assert extract_params("{{ 城市 }}{{a}}{{ 城市 }}") == ["城市", "a"]


def test_extract_empty():
    assert extract_params("") == []
    assert extract_params("没有参数") == []


def test_validate_ok():
    assert validate_template("{{ a }} 与 {{中文}}") == []
    assert validate_template("纯文本") == []


def test_validate_empty_param():
    assert any("空参数" in e for e in validate_template("hi {{ }}"))


def test_validate_illegal_char():
    assert any("非法" in e for e in validate_template("{{ a-b }}"))


def test_validate_unbalanced():
    assert validate_template("{{ a }") != []


def test_validate_nested():
    assert validate_template("{{ {{ x }} }}") != []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/common && pytest tests/test_prompt_template.py -q`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 实现**

`services/common/modelforge_common/prompt_template.py`:

```python
"""{{ name }} 模板参数:抽取与语法校验。
app-server 用于 Prompt 保存校验;train-worker 在 Prompt 评测阶段复用(render 留给子项目 C)。
"""
from __future__ import annotations

import re

__all__ = ["extract_params", "validate_template"]

# {{ name }} —— 两侧空格可选;name = 字母/数字/下划线/中文
_PARAM_RE = re.compile(r"\{\{\s*([\w一-鿿]+)\s*\}\}")
# 任意一对不含花括号的 {{ ... }}(用于校验)
_PAIR_RE = re.compile(r"\{\{([^{}]*)\}\}")
_NAME_RE = re.compile(r"[\w一-鿿]+")


def extract_params(text: str) -> list[str]:
    """抽出全部 {{ name }} 的 name(去重保序)。"""
    seen: dict[str, None] = {}
    for m in _PARAM_RE.finditer(text or ""):
        seen.setdefault(m.group(1), None)
    return list(seen)


def validate_template(text: str) -> list[str]:
    """返回错误消息列表(空 = 合法)。"""
    text = text or ""
    errors: list[str] = []
    for m in _PAIR_RE.finditer(text):
        inner = m.group(1).strip()
        if not inner:
            errors.append("存在空参数 {{ }},请填写参数名")
        elif not _NAME_RE.fullmatch(inner):
            errors.append(f"参数名非法:{{{{ {inner} }}}}(只允许字母/数字/下划线/中文)")
    residual = _PAIR_RE.sub("", text)
    if "{{" in residual or "}}" in residual:
        errors.append("花括号不成对或嵌套(请用 {{ 参数名 }})")
    out: list[str] = []
    for e in errors:
        if e not in out:
            out.append(e)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd services/common && pytest tests/test_prompt_template.py -q`
Expected: PASS(8 passed)

- [ ] **Step 5: 提交**

```bash
git add services/common/modelforge_common/prompt_template.py services/common/tests/test_prompt_template.py
git commit -m "$(printf 'feat(common): add prompt_template (param extraction + validation)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 2: Prompt 模型 + 迁移 019

**Files:**
- Create: `services/app-server/app/models/prompt.py`
- Modify: `services/app-server/app/models/__init__.py`
- Create: `services/app-server/db/migrations/019_prompts.sql`
- Test: `services/app-server/tests/test_prompts.py`

- [ ] **Step 1: 写失败测试**

`services/app-server/tests/test_prompts.py`:

```python
from tests.conftest import make_user, auth_headers


def test_prompt_models_and_latest(session_factory):
    from app.models.prompt import Prompt, PromptVersion
    db = session_factory()
    p = Prompt(name="问候")
    p.versions.append(PromptVersion(version_no=1, system_prompt="你是助手",
                                    user_prompt="你好 {{ name }}", params=["name"]))
    p.versions.append(PromptVersion(version_no=2, system_prompt="",
                                    user_prompt="{{ a }}{{ b }}", params=["a", "b"]))
    db.add(p); db.commit(); db.refresh(p)
    assert p.id and p.latest_version_no == 2 and p.latest_params == ["a", "b"]


def test_prompt_delete_cascades_versions(session_factory):
    from app.models.prompt import Prompt, PromptVersion
    from sqlalchemy import select
    db = session_factory()
    p = Prompt(name="x"); p.versions.append(PromptVersion(version_no=1))
    db.add(p); db.commit()
    db.delete(p); db.commit()
    assert db.execute(select(PromptVersion)).first() is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompts.py -q`
Expected: FAIL(`ModuleNotFoundError: app.models.prompt`)

- [ ] **Step 3: 实现模型**

`services/app-server/app/models/prompt.py`:

```python
from sqlalchemy import ForeignKey, UniqueConstraint, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, CreatorMixin


class Prompt(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    versions: Mapped[list["PromptVersion"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", back_populates="prompt",
        order_by="PromptVersion.version_no")

    @property
    def latest_version(self) -> "PromptVersion | None":
        return max(self.versions, key=lambda v: v.version_no) if self.versions else None

    @property
    def latest_version_no(self) -> int | None:
        lv = self.latest_version
        return lv.version_no if lv else None

    @property
    def latest_params(self) -> list:
        lv = self.latest_version
        return list(lv.params) if lv else []


class PromptVersion(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("prompt_id", "version_no",
                                       name="uq_prompt_versions_prompt_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column()
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    user_prompt: Mapped[str] = mapped_column(Text, default="")
    params: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    prompt: Mapped["Prompt"] = relationship(lazy="selectin", back_populates="versions")
```

- [ ] **Step 4: 注册模型**

In `services/app-server/app/models/__init__.py`, add an import after the llm import:
```python
from app.models.llm import LlmProvider, LlmModel
from app.models.prompt import Prompt, PromptVersion
```
And add to `__all__` after `"LlmModel",`:
```python
    "Prompt",
    "PromptVersion",
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompts.py -q`
Expected: PASS(2 passed)

- [ ] **Step 6: 写迁移 019**

`services/app-server/db/migrations/019_prompts.sql`:

```sql
CREATE TABLE IF NOT EXISTS prompts (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    created_by  INTEGER REFERENCES users(id),
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id            SERIAL PRIMARY KEY,
    prompt_id     INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version_no    INTEGER NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT '',
    user_prompt   TEXT NOT NULL DEFAULT '',
    params        JSON NOT NULL DEFAULT '[]',
    note          TEXT NOT NULL DEFAULT '',
    created_by    INTEGER REFERENCES users(id),
    created_at    TIMESTAMP DEFAULT now(),
    updated_at    TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_prompt_versions_prompt_no UNIQUE (prompt_id, version_no)
);
CREATE INDEX IF NOT EXISTS ix_prompt_versions_prompt ON prompt_versions(prompt_id);
```

- [ ] **Step 7: 提交**

```bash
git add services/app-server/app/models/prompt.py services/app-server/app/models/__init__.py services/app-server/db/migrations/019_prompts.sql services/app-server/tests/test_prompts.py
git commit -m "$(printf 'feat(app-server): add prompts/prompt_versions models + migration 019\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 3: 权限 `prompt:read`/`prompt:write` + 迁移 020 + 计数断言

**Files:**
- Modify: `services/app-server/app/bootstrap.py`
- Create: `services/app-server/db/migrations/020_prompt_perms.sql`
- Modify: `services/app-server/tests/test_bootstrap.py`、`services/app-server/tests/test_migrations_apply.py`
- Test: `services/app-server/tests/test_prompts.py`(追加)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompts.py`:

```python
def test_bootstrap_has_prompt_perms(session_factory):
    from app import bootstrap
    from app.models.rbac import Permission, Role
    from sqlalchemy import select
    db = session_factory()
    bootstrap.seed(db)
    codes = {p.code for p in db.execute(select(Permission)).scalars()}
    assert {"prompt:read", "prompt:write"} <= codes
    admin = db.execute(select(Role).where(Role.name == "admin")).scalar_one()
    member = db.execute(select(Role).where(Role.name == "member")).scalar_one()
    viewer = db.execute(select(Role).where(Role.name == "viewer")).scalar_one()
    assert "prompt:write" in {p.code for p in admin.permissions}
    assert "prompt:write" in {p.code for p in member.permissions}
    assert "prompt:read" in {p.code for p in viewer.permissions}
    assert "prompt:write" not in {p.code for p in viewer.permissions}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompts.py::test_bootstrap_has_prompt_perms -q`
Expected: FAIL

- [ ] **Step 3: 改 bootstrap.py**

In `services/app-server/app/bootstrap.py`, add to `PERMISSION_CATALOG` after the `("llm:manage", "LLM 供应商配置"),` line:
```python
    ("llm:manage", "LLM 供应商配置"),
    ("prompt:read", "看 Prompt"), ("prompt:write", "管理 Prompt"),
```
Change `READS` to include `prompt:read`:
```python
READS = ["dataset:read", "training:read", "model:read", "eval:read", "deploy:read", "badcase:read", "prompt:read"]
```
Change `BUSINESS` to include `prompt:write` (append to the added list):
```python
BUSINESS = READS + ["dataset:write", "training:run", "eval:run", "deploy:write", "model:write", "badcase:annotate", "prompt:write"]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompts.py::test_bootstrap_has_prompt_perms -q`
Expected: PASS

- [ ] **Step 5: 写迁移 020**

`services/app-server/db/migrations/020_prompt_perms.sql`:

```sql
INSERT INTO permissions (code, description) VALUES
  ('prompt:read', '看 Prompt'),
  ('prompt:write', '管理 Prompt')
ON CONFLICT (code) DO NOTHING;

-- prompt:read -> admin, member, viewer
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member', 'viewer') AND p.code = 'prompt:read'
ON CONFLICT DO NOTHING;

-- prompt:write -> admin, member
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member') AND p.code = 'prompt:write'
ON CONFLICT DO NOTHING;
```

- [ ] **Step 6: 更新计数断言(本子项目新增 2 表 + 2 权限)**

In `services/app-server/tests/test_bootstrap.py`, change the permission-count assertion (currently `== 17`) to `== 19`:
```python
    assert db.execute(select(func.count()).select_from(Permission)).scalar() == 19
```

In `services/app-server/tests/test_migrations_apply.py`, change the line `assert ntab == 15 and nperm == 17 and nrole == 4 and sa_perms == 1` to:
```python
    assert ntab == 17 and nperm == 19 and nrole == 4 and sa_perms == 1
```
And change the later re-check `assert c.execute(text("SELECT count(*) FROM permissions")).scalar() == 17` to:
```python
        assert c.execute(text("SELECT count(*) FROM permissions")).scalar() == 19
```

- [ ] **Step 7: 跑测试确认通过(含真实 PG 迁移测试)**

Run: `cd services/app-server && pytest tests/test_prompts.py tests/test_bootstrap.py tests/test_migrations_apply.py -q`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add services/app-server/app/bootstrap.py services/app-server/db/migrations/020_prompt_perms.sql services/app-server/tests/test_prompts.py services/app-server/tests/test_bootstrap.py services/app-server/tests/test_migrations_apply.py
git commit -m "$(printf 'feat(app-server): add prompt:read/prompt:write permissions + migration 020\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 4: `DatasetKind.PROMPT` + dataset_service prompt 分支

**Files:**
- Modify: `services/common/modelforge_common/enums.py`
- Modify: `services/app-server/app/services/dataset_service.py`
- Test: `services/app-server/tests/test_prompts.py`(追加)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompts.py`:

```python
class _FakeStore:
    def write_snapshot(self, dataset_id, version_no, df):
        return (f"mem://{dataset_id}/{version_no}", "checksum", len(df))


def test_validate_prompt_rows_rejects_empty():
    import pandas as pd, pytest
    from app.services.dataset_service import validate_prompt_rows
    with pytest.raises(ValueError):
        validate_prompt_rows(pd.DataFrame())                 # 0 列
    with pytest.raises(ValueError):
        validate_prompt_rows(pd.DataFrame(columns=["a"]))    # 0 行


def test_create_prompt_version_skips_task_validation(session_factory):
    import pandas as pd
    from app.models.dataset import Dataset
    from app.services.dataset_service import create_version
    db = session_factory()
    ds = Dataset(name="pset", kind="prompt", task_type="prompt"); db.add(ds); db.commit()
    df = pd.DataFrame([{"city": "BJ", "name": "x"}])
    v = create_version(db, _FakeStore(), ds, df, created_by=None)
    assert v.stats["columns"] == ["city", "name"] and v.version_no == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompts.py::test_validate_prompt_rows_rejects_empty tests/test_prompts.py::test_create_prompt_version_skips_task_validation -q`
Expected: FAIL(`ImportError: validate_prompt_rows` / `TaskType('prompt')` ValueError)

- [ ] **Step 3: 加 `DatasetKind.PROMPT`**

In `services/common/modelforge_common/enums.py`, add to `DatasetKind`:
```python
class DatasetKind(str, Enum):
    TRAIN = "train"      # 训练集 — model training
    EVAL = "eval"        # 评估集 — validation during training
    TEST = "test"        # 测试集 — model testing (model-test page)
    PROMPT = "prompt"    # Prompt 测试集 — 列即参数,供 Prompt 评测
```

- [ ] **Step 4: 加 prompt 分支**

In `services/app-server/app/services/dataset_service.py`, change the import line `from modelforge_common.enums import TaskType` to:
```python
from modelforge_common.enums import TaskType, DatasetKind
```
Add a `validate_prompt_rows` function right after the existing `validate_rows` function:
```python
def validate_prompt_rows(df: pd.DataFrame) -> None:
    if df.shape[1] == 0:
        raise ValueError("Prompt 测试集至少需要一列参数")
    if len(df) == 0:
        raise ValueError("dataset is empty")
```
In `create_version`, replace the first two lines of the body:
```python
    validate_rows(df, TaskType(dataset.task_type))
    df = normalize_list_columns(df, TaskType(dataset.task_type))
```
with:
```python
    if dataset.kind == DatasetKind.PROMPT.value:
        validate_prompt_rows(df)
    else:
        validate_rows(df, TaskType(dataset.task_type))
        df = normalize_list_columns(df, TaskType(dataset.task_type))
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompts.py::test_validate_prompt_rows_rejects_empty tests/test_prompts.py::test_create_prompt_version_skips_task_validation -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add services/common/modelforge_common/enums.py services/app-server/app/services/dataset_service.py services/app-server/tests/test_prompts.py
git commit -m "$(printf 'feat: add DatasetKind.PROMPT + prompt-dataset branch in create_version\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 5: Prompt schema

**Files:**
- Create: `services/app-server/app/schemas/prompt.py`
- Test: `services/app-server/tests/test_prompts.py`(追加)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompts.py`:

```python
def test_prompt_out_serializes_latest(session_factory):
    from app.models.prompt import Prompt, PromptVersion
    from app.schemas.prompt import PromptOut, PromptDetailOut
    db = session_factory()
    p = Prompt(name="x")
    p.versions.append(PromptVersion(version_no=1, system_prompt="s", user_prompt="{{ a }}", params=["a"]))
    db.add(p); db.commit(); db.refresh(p)
    out = PromptOut.model_validate(p).model_dump()
    assert out["latest_version_no"] == 1 and out["latest_params"] == ["a"]
    detail = PromptDetailOut.model_validate(p).model_dump()
    assert detail["versions"][0]["user_prompt"] == "{{ a }}"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompts.py::test_prompt_out_serializes_latest -q`
Expected: FAIL(`ModuleNotFoundError: app.schemas.prompt`)

- [ ] **Step 3: 实现 schema**

`services/app-server/app/schemas/prompt.py`:

```python
from datetime import datetime
from pydantic import BaseModel


class PromptVersionOut(BaseModel):
    id: int
    version_no: int
    system_prompt: str
    user_prompt: str
    params: list[str] = []
    note: str = ""
    created_by_name: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class PromptOut(BaseModel):
    id: int
    name: str
    created_by_name: str | None = None
    created_at: datetime
    latest_version_no: int | None = None
    latest_params: list[str] = []

    class Config:
        from_attributes = True


class PromptDetailOut(PromptOut):
    versions: list[PromptVersionOut] = []


class PromptCreate(BaseModel):
    name: str
    system_prompt: str = ""
    user_prompt: str = ""
    note: str = ""


class PromptVersionCreate(BaseModel):
    system_prompt: str = ""
    user_prompt: str = ""
    note: str = ""


class PromptValidateIn(BaseModel):
    system_prompt: str = ""
    user_prompt: str = ""


class PromptValidateOut(BaseModel):
    params: list[str]
    errors: list[str]


class PromptDatasetCreate(BaseModel):
    name: str
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompts.py::test_prompt_out_serializes_latest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/app-server/app/schemas/prompt.py services/app-server/tests/test_prompts.py
git commit -m "$(printf 'feat(app-server): add prompt schemas\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 6: `prompt_service`

**Files:**
- Create: `services/app-server/app/services/prompt_service.py`
- Test: `services/app-server/tests/test_prompts.py`(追加)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompts.py`:

```python
def test_prompt_service_create_and_version(session_factory):
    from app.services import prompt_service as svc
    db = session_factory()
    p = svc.create_prompt(db, name="问候", system_prompt="你是 {{ role }}",
                          user_prompt="你好 {{ name }}", note="", created_by=None)
    assert p.versions[0].version_no == 1
    assert p.versions[0].params == ["role", "name"]   # system ∪ user, 保序
    v2 = svc.add_version(db, p.id, system_prompt="", user_prompt="{{ name }}{{ name }}",
                         note="", created_by=None)
    assert v2.version_no == 2 and v2.params == ["name"]
    # 不存在的 prompt
    assert svc.add_version(db, 99999, system_prompt="", user_prompt="", note="", created_by=None) is None
    # 语法错误 -> ValueError
    import pytest
    with pytest.raises(ValueError):
        svc.create_prompt(db, name="bad", system_prompt="{{ }}", user_prompt="",
                          note="", created_by=None)


def test_prompt_service_validate():
    from app.services import prompt_service as svc
    ok = svc.validate("{{ a }}", "{{ b }}")
    assert ok["params"] == ["a", "b"] and ok["errors"] == []
    bad = svc.validate("{{ a-b }}", "")
    assert bad["errors"] != []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompts.py::test_prompt_service_create_and_version tests/test_prompts.py::test_prompt_service_validate -q`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 实现 service**

`services/app-server/app/services/prompt_service.py`:

```python
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from modelforge_common.prompt_template import extract_params, validate_template
from app.models.prompt import Prompt, PromptVersion


def _params_of(system_prompt: str, user_prompt: str) -> list[str]:
    out: list[str] = []
    for name in extract_params(system_prompt) + extract_params(user_prompt):
        if name not in out:
            out.append(name)
    return out


def validate(system_prompt: str, user_prompt: str) -> dict:
    errors = validate_template(system_prompt) + validate_template(user_prompt)
    return {"params": _params_of(system_prompt, user_prompt), "errors": errors}


def create_prompt(db: Session, *, name: str, system_prompt: str, user_prompt: str,
                  note: str, created_by: int | None) -> Prompt:
    errs = validate_template(system_prompt) + validate_template(user_prompt)
    if errs:
        raise ValueError("; ".join(errs))
    p = Prompt(name=name, created_by=created_by)
    p.versions.append(PromptVersion(
        version_no=1, system_prompt=system_prompt, user_prompt=user_prompt,
        params=_params_of(system_prompt, user_prompt), note=note, created_by=created_by))
    db.add(p); db.commit(); db.refresh(p)
    return p


def add_version(db: Session, prompt_id: int, *, system_prompt: str, user_prompt: str,
                note: str, created_by: int | None) -> PromptVersion | None:
    p = db.get(Prompt, prompt_id)
    if not p:
        return None
    errs = validate_template(system_prompt) + validate_template(user_prompt)
    if errs:
        raise ValueError("; ".join(errs))
    next_no = (db.execute(
        select(func.coalesce(func.max(PromptVersion.version_no), 0))
        .where(PromptVersion.prompt_id == prompt_id)).scalar()) + 1
    v = PromptVersion(prompt_id=prompt_id, version_no=next_no, system_prompt=system_prompt,
                      user_prompt=user_prompt, params=_params_of(system_prompt, user_prompt),
                      note=note, created_by=created_by)
    db.add(v); db.commit(); db.refresh(v)
    return v
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompts.py::test_prompt_service_create_and_version tests/test_prompts.py::test_prompt_service_validate -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/app-server/app/services/prompt_service.py services/app-server/tests/test_prompts.py
git commit -m "$(printf 'feat(app-server): add prompt_service (create/add_version/validate)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 7: `/prompts` API + `/datasets/prompt` + 注册

**Files:**
- Create: `services/app-server/app/api/prompt.py`
- Modify: `services/app-server/app/api/datasets.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_prompts.py`(追加)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompts.py`:

```python
import io
import boto3
import pandas as pd
from moto import mock_aws
from fastapi.testclient import TestClient


def _client(session_factory, codes):
    db = session_factory()
    u = make_user(db, codes=codes, data_scope="all", email="pr@x.com"); db.close()
    from app.main import app
    return TestClient(app), auth_headers(u.id)


def test_prompt_api_flow(session_factory):
    c, H = _client(session_factory, ("prompt:read", "prompt:write"))
    # validate
    v = c.post("/prompts/validate", json={"system_prompt": "{{ a }}", "user_prompt": "{{ b }}"}, headers=H).json()
    assert v["params"] == ["a", "b"] and v["errors"] == []
    # create
    r = c.post("/prompts", json={"name": "问候", "system_prompt": "你是 {{ role }}",
               "user_prompt": "你好 {{ name }}"}, headers=H)
    assert r.status_code == 201
    body = r.json(); pid = body["id"]
    assert body["latest_version_no"] == 1 and body["versions"][0]["params"] == ["role", "name"]
    # invalid syntax -> 422
    assert c.post("/prompts", json={"name": "bad", "system_prompt": "{{ }}", "user_prompt": ""}, headers=H).status_code == 422
    # add version
    av = c.post(f"/prompts/{pid}/versions", json={"system_prompt": "", "user_prompt": "{{ x }}"}, headers=H)
    assert av.status_code == 201 and av.json()["version_no"] == 2
    # list + get + versions
    assert c.get("/prompts", headers=H).json()[0]["id"] == pid
    assert c.get(f"/prompts/{pid}", headers=H).json()["latest_version_no"] == 2
    assert len(c.get(f"/prompts/{pid}/versions", headers=H).json()) == 2
    # 404
    assert c.get("/prompts/99999", headers=H).status_code == 404


def test_prompt_api_requires_perm(session_factory):
    c, H = _client(session_factory, ("dataset:read",))
    assert c.get("/prompts", headers=H).status_code == 403


@mock_aws
def test_prompt_dataset_endpoint(tmp_path):
    # 上传走真实存储路径,按既有 dataset 上传测试的套路:@mock_aws + 建桶 + 手动建 engine
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="datasets")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    eng = create_engine(f"sqlite:///{tmp_path}/t.db"); Base.metadata.create_all(eng)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    d = dbmod.SessionLocal()
    u = make_user(d, codes=("dataset:read", "dataset:write"), data_scope="all", email="pds@x.com")
    H = auth_headers(u.id); d.close()
    from app.main import app
    c = TestClient(app)
    r = c.post("/datasets/prompt", json={"name": "城市集"}, headers=H)
    assert r.status_code == 201
    ds = r.json()
    assert ds["kind"] == "prompt" and ds["task_type"] == "prompt"
    # 上传一版:列即参数,存进 stats.columns(create_version 已对所有 kind 写 stats.columns)
    df = pd.DataFrame({"city": ["BJ", "SH"], "name": ["xiaoming", "lily"]})
    buf = io.BytesIO(); df.to_csv(buf, index=False); buf.seek(0)
    up = c.post(f"/datasets/{ds['id']}/versions",
                files={"file": ("p.csv", buf, "text/csv")}, headers=H)
    assert up.status_code == 201 and up.json()["row_count"] == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompts.py::test_prompt_api_flow tests/test_prompts.py::test_prompt_dataset_endpoint -q`
Expected: FAIL(404 路由不存在)

- [ ] **Step 3: 实现 prompt 路由**

`services/app-server/app/api/prompt.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.models.prompt import Prompt, PromptVersion
from app.schemas.prompt import (PromptOut, PromptDetailOut, PromptVersionOut,
                                PromptCreate, PromptVersionCreate,
                                PromptValidateIn, PromptValidateOut)
from app.services import prompt_service as svc
from app.pagination import paginate

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("", response_model=list[PromptOut])
def list_prompts(response: Response, page: int | None = Query(None, ge=1),
                 page_size: int = Query(20, ge=1, le=200),
                 _: User = Depends(require("prompt:read")), db: Session = Depends(get_db)):
    stmt = select(Prompt).order_by(Prompt.id.desc())
    return paginate(db, stmt, response, page, page_size)


@router.post("", response_model=PromptDetailOut, status_code=201)
def create_prompt(body: PromptCreate, user: User = Depends(require("prompt:write")),
                  db: Session = Depends(get_db)):
    try:
        return svc.create_prompt(db, name=body.name, system_prompt=body.system_prompt,
                                 user_prompt=body.user_prompt, note=body.note, created_by=user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/validate", response_model=PromptValidateOut)
def validate_prompt(body: PromptValidateIn, _: User = Depends(require("prompt:read"))):
    return svc.validate(body.system_prompt, body.user_prompt)


@router.get("/{prompt_id}", response_model=PromptDetailOut)
def get_prompt(prompt_id: int, _: User = Depends(require("prompt:read")),
               db: Session = Depends(get_db)):
    p = db.get(Prompt, prompt_id)
    if not p:
        raise HTTPException(404, "prompt not found")
    return p


@router.get("/{prompt_id}/versions", response_model=list[PromptVersionOut])
def list_versions(prompt_id: int, response: Response, page: int | None = Query(None, ge=1),
                  page_size: int = Query(20, ge=1, le=200),
                  _: User = Depends(require("prompt:read")), db: Session = Depends(get_db)):
    if not db.get(Prompt, prompt_id):
        raise HTTPException(404, "prompt not found")
    stmt = (select(PromptVersion).where(PromptVersion.prompt_id == prompt_id)
            .order_by(PromptVersion.version_no.desc()))
    return paginate(db, stmt, response, page, page_size)


@router.post("/{prompt_id}/versions", response_model=PromptVersionOut, status_code=201)
def add_version(prompt_id: int, body: PromptVersionCreate,
                user: User = Depends(require("prompt:write")), db: Session = Depends(get_db)):
    try:
        v = svc.add_version(db, prompt_id, system_prompt=body.system_prompt,
                            user_prompt=body.user_prompt, note=body.note, created_by=user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if v is None:
        raise HTTPException(404, "prompt not found")
    return v
```

- [ ] **Step 4: 加 `/datasets/prompt` 端点**

In `services/app-server/app/api/datasets.py`, add `PromptDatasetCreate` to the imports from prompt schemas (add this import line near the other `from app.schemas...` imports):
```python
from app.schemas.prompt import PromptDatasetCreate
```
Add this endpoint right after the existing `create_dataset` function (the `@router.post("", ...)` one):
```python
@router.post("/prompt", response_model=DatasetOut, status_code=201)
def create_prompt_dataset(body: PromptDatasetCreate,
                          user: User = Depends(require("dataset:write")),
                          db: Session = Depends(get_db)):
    ds = Dataset(name=body.name, kind="prompt", task_type="prompt", created_by=user.id)
    db.add(ds); db.commit(); db.refresh(ds)
    return ds
```

- [ ] **Step 5: 注册 prompt 路由**

In `services/app-server/app/main.py`, at the END (after the `llm` router block), add:
```python
from app.api import prompt
app.include_router(prompt.router)
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompts.py -q`
Expected: PASS(全部 prompt 测试通过)

- [ ] **Step 7: 跑 app-server 全量回归**

Run: `cd services/app-server && pytest -q`
Expected: PASS(无回归;计数断言已在 T3 更新)

- [ ] **Step 8: 提交**

```bash
git add services/app-server/app/api/prompt.py services/app-server/app/api/datasets.py services/app-server/app/main.py services/app-server/tests/test_prompts.py
git commit -m "$(printf 'feat(app-server): add /prompts API + /datasets/prompt endpoint\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 8: 前端 API client

**Files:**
- Modify: `frontend/src/api/client.ts`

> 验证 = `npx tsc --noEmit -p tsconfig.app.json`。

- [ ] **Step 1: 加类型与函数**

In `frontend/src/api/client.ts`, after the line `export const createDataset = (b: { name: string; kind: string; task_type: string }) => ...` (the one near the top that creates datasets), add on the next line:
```typescript
export const createPromptDataset = (b: { name: string }) =>
  api.post<Dataset>("/datasets/prompt", b).then(r => r.data);
```

At the END of the file, append the prompt client:
```typescript
export type PromptVersionRow = {
  id: number; version_no: number; system_prompt: string; user_prompt: string;
  params: string[]; note: string; created_by_name: string | null; created_at: string;
};
export type Prompt = {
  id: number; name: string; created_by_name: string | null; created_at: string;
  latest_version_no: number | null; latest_params: string[];
};
export type PromptDetail = Prompt & { versions: PromptVersionRow[] };
export const listPromptsPaged = (p: { page: number; page_size: number }) =>
  getPaginated<Prompt>("/prompts", p);
export const getPrompt = (id: number) => api.get<PromptDetail>(`/prompts/${id}`).then(r => r.data);
export const createPrompt = (b: { name: string; system_prompt: string; user_prompt: string; note?: string }) =>
  api.post<PromptDetail>("/prompts", b).then(r => r.data);
export const addPromptVersion = (id: number, b: { system_prompt: string; user_prompt: string; note?: string }) =>
  api.post<PromptVersionRow>(`/prompts/${id}/versions`, b).then(r => r.data);
export const validatePrompt = (b: { system_prompt: string; user_prompt: string }) =>
  api.post<{ params: string[]; errors: string[] }>("/prompts/validate", b).then(r => r.data);
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
Expected: no errors

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/client.ts
git commit -m "$(printf 'feat(frontend): add prompt + prompt-dataset api client\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 9: 前端 Prompt 页 + 路由 + 导航

**Files:**
- Create: `frontend/src/pages/PromptsPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`

- [ ] **Step 1: 写 Prompt 页**

Create `frontend/src/pages/PromptsPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { MessageSquareText, Plus, History, GitBranch } from "lucide-react";
import {
  listPromptsPaged, createPrompt, addPromptVersion, getPrompt, validatePrompt,
  type Prompt, type PromptDetail,
} from "../api/client";
import {
  Badge, Button, Drawer, EmptyState, Field, Input, PageHeader, Pagination,
  TableShell, Creator, CreatedAt,
} from "../ui";
import { toastError, toastSuccess } from "../toast";

function ParamChips({ params }: { params: string[] }) {
  if (params.length === 0) return <span className="text-slate-400">无参数</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {params.map(p => <Badge key={p} tone="blue">{p}</Badge>)}
    </div>
  );
}

function Editor({
  edit, onClose, onSaved,
}: { edit: { mode: "new" } | { mode: "version"; prompt: Prompt }; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [sys, setSys] = useState("");
  const [usr, setUsr] = useState("");
  const [params, setParams] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      validatePrompt({ system_prompt: sys, user_prompt: usr })
        .then(r => { setParams(r.params); setErrors(r.errors); })
        .catch(() => {});
    }, 300);
    return () => clearTimeout(t);
  }, [sys, usr]);

  const save = async () => {
    setBusy(true);
    try {
      if (edit.mode === "new") {
        await createPrompt({ name, system_prompt: sys, user_prompt: usr });
      } else {
        await addPromptVersion(edit.prompt.id, { system_prompt: sys, user_prompt: usr });
      }
      toastSuccess("已保存");
      onSaved(); onClose();
    } catch (e: any) {
      toastError(e?.response?.data?.detail ?? "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const canSave = errors.length === 0 && (edit.mode === "version" || name.trim().length > 0);

  return (
    <Drawer
      open
      onClose={onClose}
      title={edit.mode === "new" ? "新建 Prompt" : `为「${edit.prompt.name}」新增版本`}
      subtitle="参数写法:{{ 参数名 }}(支持中文)。system 与 user 的参数取并集。"
      width="max-w-2xl"
      footer={
        <div className="flex items-center justify-end gap-2">
          <Button variant="subtle" disabled={busy} onClick={onClose}>取消</Button>
          <Button variant="primary" disabled={!canSave} loading={busy} onClick={save}>保存为新版本</Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        {edit.mode === "new" && (
          <Field label="名称"><Input value={name} onChange={e => setName(e.target.value)} placeholder="如:售前意图分类 prompt" /></Field>
        )}
        <Field label="System Prompt">
          <textarea value={sys} onChange={e => setSys(e.target.value)} rows={5}
            className="w-full rounded-lg bg-white px-3 py-2 text-sm text-slate-900 ring-1 ring-slate-200 outline-none transition focus:ring-2 focus:ring-brand-500 placeholder:text-slate-400 font-mono"
            placeholder="你是一个{{ 角色 }}…" />
        </Field>
        <Field label="User Prompt">
          <textarea value={usr} onChange={e => setUsr(e.target.value)} rows={6}
            className="w-full rounded-lg bg-white px-3 py-2 text-sm text-slate-900 ring-1 ring-slate-200 outline-none transition focus:ring-2 focus:ring-brand-500 placeholder:text-slate-400 font-mono"
            placeholder="请处理:{{ 输入 }}" />
        </Field>
        <div>
          <div className="label mb-1.5">识别到的参数</div>
          <ParamChips params={params} />
        </div>
        {errors.length > 0 && (
          <div className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600 ring-1 ring-red-100">
            {errors.map((e, i) => <div key={i}>{e}</div>)}
          </div>
        )}
      </div>
    </Drawer>
  );
}

function HistoryDrawer({ promptId, onClose }: { promptId: number; onClose: () => void }) {
  const [detail, setDetail] = useState<PromptDetail | null>(null);
  useEffect(() => { getPrompt(promptId).then(setDetail).catch(() => toastError("加载失败")); }, [promptId]);
  return (
    <Drawer open onClose={onClose} title="版本历史" subtitle={detail?.name} width="max-w-2xl">
      <div className="flex flex-col gap-3">
        {(detail?.versions ?? []).slice().reverse().map(v => (
          <div key={v.id} className="rounded-xl border border-slate-200 p-3">
            <div className="mb-2 flex items-center gap-2">
              <Badge tone="gray">V{v.version_no}</Badge>
              <ParamChips params={v.params} />
              <span className="ml-auto text-[12px] text-slate-400"><CreatedAt at={v.created_at} /></span>
            </div>
            {v.system_prompt && <pre className="mb-1 whitespace-pre-wrap rounded bg-slate-50 p-2 text-[12px] text-slate-700">[system] {v.system_prompt}</pre>}
            <pre className="whitespace-pre-wrap rounded bg-slate-50 p-2 text-[12px] text-slate-700">[user] {v.user_prompt}</pre>
          </div>
        ))}
      </div>
    </Drawer>
  );
}

export function PromptsPage() {
  const [items, setItems] = useState<Prompt[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [editor, setEditor] = useState<{ mode: "new" } | { mode: "version"; prompt: Prompt } | null>(null);
  const [historyId, setHistoryId] = useState<number | null>(null);

  const reload = () => listPromptsPaged({ page, page_size: pageSize })
    .then(res => { setItems(res.items); setTotal(res.total); });
  useEffect(() => { setLoading(true); reload().finally(() => setLoading(false)); }, [page, pageSize]);

  return (
    <>
      <PageHeader
        title="Prompt"
        subtitle="管理带 {{ 参数 }} 的 system / user prompt,版本化,供 Prompt 评测选用。"
        actions={<Button variant="primary" onClick={() => setEditor({ mode: "new" })}><Plus size={16} /> 新建 Prompt</Button>}
      />

      <TableShell
        loading={loading}
        empty={items.length === 0}
        head={<><th>名称</th><th>最新版本</th><th>参数</th><th>创建者</th><th className="w-36">创建时间</th><th className="w-48 text-right"></th></>}
      >
        {items.length === 0 ? (
          <EmptyState icon={<MessageSquareText size={22} />} title="还没有 Prompt" hint="新建一个带 {{ 参数 }} 的 prompt。" />
        ) : items.map(p => (
          <tr key={p.id}>
            <td className="font-medium text-slate-800">{p.name}</td>
            <td>{p.latest_version_no ? <Badge tone="gray">V{p.latest_version_no}</Badge> : "—"}</td>
            <td className="wrap"><ParamChips params={p.latest_params} /></td>
            <td><Creator name={p.created_by_name} /></td>
            <td><CreatedAt at={p.created_at} /></td>
            <td className="text-right">
              <div className="flex items-center justify-end gap-2">
                <Button size="sm" onClick={() => setEditor({ mode: "version", prompt: p })}><GitBranch size={13} /> 新增版本</Button>
                <Button size="sm" onClick={() => setHistoryId(p.id)}><History size={13} /> 历史</Button>
              </div>
            </td>
          </tr>
        ))}
      </TableShell>
      <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />

      {editor && <Editor edit={editor} onClose={() => setEditor(null)} onSaved={reload} />}
      {historyId !== null && <HistoryDrawer promptId={historyId} onClose={() => setHistoryId(null)} />}
    </>
  );
}
```

- [ ] **Step 2: 注册路由**

In `frontend/src/App.tsx`, add an import alongside other page imports:
```tsx
import { PromptsPage } from "./pages/PromptsPage";
```
And add a route line after the `/settings` branch:
```tsx
  else if (path === "/prompts") page = <PromptsPage />;
```

- [ ] **Step 3: 加导航项**

In `frontend/src/components/AppShell.tsx`: add `MessageSquareText` to the `lucide-react` import; in the `NAV` array, add an entry after the badcase entry:
```tsx
  { href: "/prompts", label: "Prompt", icon: <MessageSquareText size={18} />, perm: "prompt:read", match: p => p.startsWith("/prompts") },
```

- [ ] **Step 4: 类型检查 + 构建**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm run build`
Expected: no type errors; build succeeds.

If a `ui` component prop differs from what the page assumes, open `frontend/src/ui.tsx` and adjust usage minimally to match (do not invent props). The `Drawer` `width` prop and `Badge` `tone` values are used elsewhere (see DeployPage / BadcaseRulesDrawer) — verify they accept these values.

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/PromptsPage.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx
git commit -m "$(printf 'feat(frontend): add Prompt management page\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 10: 数据集页集成 Prompt 测试集

**Files:**
- Modify: `frontend/src/pages/DatasetsPage.tsx`

- [ ] **Step 1: 读现状**

Open `frontend/src/pages/DatasetsPage.tsx`. Confirm: `KIND_LABEL` (line ~17) maps train/eval/test; the create drawer has a `kind` `<Select>` and a `task` `<Select>`; `submit` calls `createDataset({ name, kind, task_type: taskType })`; the import line pulls `createDataset` from `../api/client`.

- [ ] **Step 2: 加 prompt 类型支持**

Change the import to also bring `createPromptDataset`:
```tsx
import { listDatasetsPaged, createDataset, createPromptDataset, downloadTemplateByType, type Dataset, type TemplateFormat } from "../api/client";
```
Add prompt to `KIND_LABEL`:
```tsx
const KIND_LABEL: Record<string, string> = { train: "训练集", eval: "评估集", test: "测试集", prompt: "Prompt 测试集" };
```
Change `submit` so prompt datasets use the dedicated endpoint (no task_type). Replace the existing `createDataset(...)` call inside `submit` with:
```tsx
    const req = kind === "prompt"
      ? createPromptDataset({ name })
      : createDataset({ name, kind, task_type: taskType });
    req.then(() => { setOpen(false); reload(); })
```
(keep the existing `.catch(...)`/`.finally(...)` chain that follows.)

In the create drawer, add a `prompt` option to the kind `<Select>` (after the existing test option):
```tsx
              <option value="prompt">Prompt 测试集</option>
```
Make the task `<Select>` field only render for non-prompt kinds. Wrap the existing `<Field label="任务">…</Field>` so it is hidden when `kind === "prompt"`:
```tsx
              {kind !== "prompt" && (
                <Field label="任务"><Select value={taskType} onChange={e => setTaskType(e.target.value)}>
                  {/* ...existing task options unchanged... */}
                </Select></Field>
              )}
```
For the prompt kind, add a one-line hint below the kind select:
```tsx
              {kind === "prompt" && <p className="text-[12px] text-slate-400">Prompt 测试集的列即参数,上传 CSV/JSONL 后自动识别,无需选择任务。</p>}
```

- [ ] **Step 3: 类型检查 + 构建**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 4: 提交**

```bash
git add frontend/src/pages/DatasetsPage.tsx
git commit -m "$(printf 'feat(frontend): support Prompt test sets (kind=prompt) on datasets page\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## 收尾验证(全部任务后)

- [ ] `cd services/common && pytest -q` 全绿;`cd services/app-server && pytest -q` 全绿(含真实 PG 迁移计数 17 表 / 19 权限)。
- [ ] 前端 `npx tsc --noEmit -p tsconfig.app.json` 与 `npm run build` 通过。
- [ ] 手动冒烟:重启 app-server(迁移 019/020 自动应用)→ admin 登录 →「Prompt」可见 → 新建 Prompt(system/user 带 `{{参数}}`,实时看到参数 chips,非法 `{{` 被拒)→ 新增版本(V2)→ 历史可见 → 数据集页新建「Prompt 测试集」并上传 CSV,列被识别。
- [ ] 无 `prompt:read` 账号看不到「Prompt」入口,`GET /prompts` 返回 403。

---

## 自审记录(对照 spec)

- **Spec 覆盖**:模板工具 extract+validate(T1)、Prompt 模型+迁移 019(T2)、prompt 权限+迁移 020+bootstrap+计数(T3)、DatasetKind.PROMPT + create_version 分支(T4)、schema(T5)、service(T6)、`/prompts` API + `/datasets/prompt`(T7)、前端 client(T8)、Prompt 页(T9)、数据集页 prompt 类型(T10)。render/coverage 按 spec 明确留给 C。
- **占位符**:无;每个代码步给完整代码与确切命令。
- **类型一致**:`extract_params`/`validate_template`(T1)被 `prompt_service`(T6)与端点(T7)调用一致;`_params_of` 并集逻辑与测试断言(`["role","name"]`)一致;模型 `latest_version_no`/`latest_params` 属性(T2)↔ `PromptOut`(T5)字段一致;`PromptDatasetCreate`(T5)↔ `/datasets/prompt`(T7)一致;`create_version` 的 prompt 分支(T4)↔ `/datasets/{id}/versions` 上传(T7 测试)一致;前端 `Prompt`/`PromptDetail`/`PromptVersionRow`(T8)↔ `PromptsPage`(T9)一致;`createPromptDataset`(T8)↔ DatasetsPage(T10)一致。
- **计数**:T3 统一把 test_bootstrap(→19)、test_migrations_apply(→17 表/19 权限,两处)更新到位,T7 全量回归确认。
