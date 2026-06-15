# 子项目 C1:Prompt 评测引擎 + 三种评测 + 数据模型 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 发起三种 Prompt 评测(多 prompt 盲测 / 多模型盲测 / 单 prompt 版本对比),worker 调用大模型把测试集每行 × 每臂批量产出结果(状态=待评估),为 C2 的人工评估备好数据。

**Architecture:** 统一数据模型 run / arm / item / output;app-server 校验(prompt 参数 ⊆ 测试集字段)+ 建 run/arms + 派发 Celery;train-worker 渲染模板、调 `llm_client`(A)、写 outputs、报进度;`prompt_template.render`(补 B 遗留)。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + 编号 SQL 迁移;Celery worker(原始 SQL);httpx via llm_client;pytest;React + TS + Vite。

**Spec:** [`docs/superpowers/specs/2026-06-15-prompt-eval-C1-eval-engine-design.md`](../specs/2026-06-15-prompt-eval-C1-eval-engine-design.md)

**铁律(`CLAUDE.md`)**:改 `app/models/**` 必配【下一个编号】幂等迁移;改 RBAC 时 `bootstrap.py` 与迁移两处一起改;**app-server 与 train-worker 互不 import**(worker 用原始 SQL + 共享 `modelforge_common`);macOS worker `--pool=solo`。当前最新迁移 `020`,本计划新增 `021`、`022`。提交以 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` 结尾。

## 文件结构

| 文件 | 职责 | 任务 |
|---|---|---|
| `services/common/modelforge_common/prompt_template.py` | 加 `render()` | T1 |
| `services/common/modelforge_common/task_names.py` | 加 `PROMPT_EVAL_TASK` | T1 |
| `services/common/tests/test_prompt_template.py` | render 单测 | T1 |
| `services/app-server/app/models/prompt_eval.py` | 4 个模型 | T2 |
| `services/app-server/app/models/__init__.py` | 注册 | T2 |
| `services/app-server/db/migrations/021_prompt_evals.sql` | 4 表 | T2 |
| `services/app-server/app/bootstrap.py` + `db/migrations/022_prompteval_perms.sql` | 权限 | T3 |
| `tests/test_bootstrap.py`、`tests/test_migrations_apply.py` | 计数(21/21) | T3 |
| `services/app-server/app/schemas/prompt_eval.py` | schema | T4 |
| `services/app-server/app/services/prompt_eval_service.py` + `app/celery_client.py` | 校验+建模+派发 | T5 |
| `services/app-server/app/api/prompt_eval.py` + `app/main.py` | `/prompt-evals` + options | T6 |
| `services/app-server/tests/test_prompt_eval.py` | service/API 测试 | T2,T5,T6 |
| `services/train-worker/worker/prompt_eval.py` + `worker/db.py` + `worker/tasks.py` | worker 引擎 | T7 |
| `services/train-worker/tests/test_prompt_eval_worker.py` | worker 测试 | T7 |
| `frontend/src/api/client.ts` | client | T8 |
| `frontend/src/pages/PromptEvalsPage.tsx` + `App.tsx` + `AppShell.tsx` | 页面 | T9 |

---

### Task 1: `render()` + task name(common)

**Files:**
- Modify: `services/common/modelforge_common/prompt_template.py`
- Modify: `services/common/modelforge_common/task_names.py`
- Test: `services/common/tests/test_prompt_template.py` (APPEND)

- [ ] **Step 1: 追加失败测试**

Append to `services/common/tests/test_prompt_template.py`:

```python
def test_render_basic():
    from modelforge_common.prompt_template import render
    assert render("你好 {{ name }}", {"name": "小明"}) == "你好 小明"


def test_render_missing_and_types():
    from modelforge_common.prompt_template import render
    assert render("{{ a }}-{{ b }}", {"a": 1}) == "1-"        # 缺参数→空;数字→str
    assert render("{{ x }}", {"x": None}) == ""               # None→空
    assert render("no params", {}) == "no params"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/common && pytest tests/test_prompt_template.py -q`
Expected: FAIL(`ImportError: cannot import name 'render'`)

- [ ] **Step 3: 实现 render**

In `services/common/modelforge_common/prompt_template.py`, add `"render"` to `__all__` and append this function at the end:

```python
def render(template: str, values: dict) -> str:
    """把 {{ name }} 替换为 str(values.get(name, ""));None / 缺失 → 空串。"""
    def _sub(m):
        v = values.get(m.group(1))
        return "" if v is None else str(v)
    return _PARAM_RE.sub(_sub, template or "")
```

(`_PARAM_RE` already exists in this module and captures the param name in group 1.)

- [ ] **Step 4: 加 task name**

In `services/common/modelforge_common/task_names.py`, add:
```python
PROMPT_EVAL_TASK = "modelforge.prompt_eval"
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd services/common && pytest tests/test_prompt_template.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add services/common/modelforge_common/prompt_template.py services/common/modelforge_common/task_names.py services/common/tests/test_prompt_template.py
git commit -m "$(printf 'feat(common): add prompt_template.render + PROMPT_EVAL_TASK name\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 2: 4 个模型 + 迁移 021

**Files:**
- Create: `services/app-server/app/models/prompt_eval.py`
- Modify: `services/app-server/app/models/__init__.py`
- Create: `services/app-server/db/migrations/021_prompt_evals.sql`
- Test: `services/app-server/tests/test_prompt_eval.py`

- [ ] **Step 1: 写失败测试**

Create `services/app-server/tests/test_prompt_eval.py`:

```python
from tests.conftest import make_user, auth_headers


def test_prompt_eval_models(session_factory):
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem, PromptEvalOutput
    db = session_factory()
    run = PromptEvalRun(name="r1", eval_type="multi_prompt",
                        prompt_version_ids=[1, 2], model_ids=[3], dataset_version_ids=[4])
    run.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=1, model_id=3, label="A"))
    run.arms.append(PromptEvalArm(arm_index=1, prompt_version_id=2, model_id=3, label="B"))
    db.add(run); db.commit(); db.refresh(run)
    assert run.id and [a.label for a in run.arms] == ["A", "B"]
    it = PromptEvalItem(run_id=run.id, item_index=0, dataset_version_id=4, row_index=0,
                        inputs={"city": "BJ"})
    it.outputs.append(PromptEvalOutput(arm_id=run.arms[0].id, output_text="hi", status="done"))
    db.add(it); db.commit(); db.refresh(it)
    assert it.outputs[0].output_text == "hi" and it.outputs[0].status == "done"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py -q`
Expected: FAIL(`ModuleNotFoundError: app.models.prompt_eval`)

- [ ] **Step 3: 实现模型**

Create `services/app-server/app/models/prompt_eval.py`:

```python
from sqlalchemy import ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, CreatorMixin


class PromptEvalRun(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "prompt_eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    eval_type: Mapped[str] = mapped_column()        # multi_prompt / multi_model / single_prompt
    status: Mapped[str] = mapped_column(default="pending")
    progress: Mapped[float] = mapped_column(default=0.0)
    celery_task_id: Mapped[str | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(nullable=True)
    prompt_version_ids: Mapped[list] = mapped_column(JSON, default=list)
    model_ids: Mapped[list] = mapped_column(JSON, default=list)
    dataset_version_ids: Mapped[list] = mapped_column(JSON, default=list)
    compare_to_version_id: Mapped[int | None] = mapped_column(nullable=True)
    result_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    arms: Mapped[list["PromptEvalArm"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", back_populates="run",
        order_by="PromptEvalArm.arm_index")


class PromptEvalArm(Base, TimestampMixin):
    __tablename__ = "prompt_eval_arms"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("prompt_eval_runs.id", ondelete="CASCADE"))
    arm_index: Mapped[int] = mapped_column()
    prompt_version_id: Mapped[int] = mapped_column(ForeignKey("prompt_versions.id"))
    model_id: Mapped[int] = mapped_column(ForeignKey("llm_models.id"))
    label: Mapped[str] = mapped_column(default="")
    run: Mapped["PromptEvalRun"] = relationship(lazy="selectin", back_populates="arms")


class PromptEvalItem(Base, TimestampMixin):
    __tablename__ = "prompt_eval_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("prompt_eval_runs.id", ondelete="CASCADE"))
    item_index: Mapped[int] = mapped_column()
    dataset_version_id: Mapped[int] = mapped_column()
    row_index: Mapped[int] = mapped_column()
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    outputs: Mapped[list["PromptEvalOutput"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", back_populates="item",
        order_by="PromptEvalOutput.id")


class PromptEvalOutput(Base, TimestampMixin):
    __tablename__ = "prompt_eval_outputs"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("prompt_eval_items.id", ondelete="CASCADE"))
    arm_id: Mapped[int] = mapped_column(ForeignKey("prompt_eval_arms.id"))
    output_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(default="pending")   # pending / done / error
    error: Mapped[str | None] = mapped_column(nullable=True)
    latency_ms: Mapped[int] = mapped_column(default=0)
    item: Mapped["PromptEvalItem"] = relationship(lazy="selectin", back_populates="outputs")
```

> 注意:`PromptEvalRun` 故意**不**建 `items` selectin 关系——否则列出 runs 时会级联加载全部 items/outputs。items 由 API 按 run_id 单独分页查询。

- [ ] **Step 4: 注册模型**

In `services/app-server/app/models/__init__.py`, add after the prompt import:
```python
from app.models.prompt import Prompt, PromptVersion
from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem, PromptEvalOutput
```
And add to `__all__` after `"PromptVersion",`:
```python
    "PromptEvalRun",
    "PromptEvalArm",
    "PromptEvalItem",
    "PromptEvalOutput",
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py -q`
Expected: PASS

- [ ] **Step 6: 写迁移 021**

Create `services/app-server/db/migrations/021_prompt_evals.sql`:

```sql
CREATE TABLE IF NOT EXISTS prompt_eval_runs (
    id                    SERIAL PRIMARY KEY,
    name                  TEXT NOT NULL,
    eval_type             TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'pending',
    progress              DOUBLE PRECISION NOT NULL DEFAULT 0,
    celery_task_id        TEXT,
    error                 TEXT,
    prompt_version_ids    JSON NOT NULL DEFAULT '[]',
    model_ids             JSON NOT NULL DEFAULT '[]',
    dataset_version_ids   JSON NOT NULL DEFAULT '[]',
    compare_to_version_id INTEGER,
    result_summary        JSON NOT NULL DEFAULT '{}',
    created_by            INTEGER REFERENCES users(id),
    created_at            TIMESTAMP DEFAULT now(),
    updated_at            TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prompt_eval_arms (
    id                SERIAL PRIMARY KEY,
    run_id            INTEGER NOT NULL REFERENCES prompt_eval_runs(id) ON DELETE CASCADE,
    arm_index         INTEGER NOT NULL,
    prompt_version_id INTEGER NOT NULL REFERENCES prompt_versions(id),
    model_id          INTEGER NOT NULL REFERENCES llm_models(id),
    label             TEXT NOT NULL DEFAULT '',
    created_at        TIMESTAMP DEFAULT now(),
    updated_at        TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_prompt_eval_arms_run ON prompt_eval_arms(run_id);

CREATE TABLE IF NOT EXISTS prompt_eval_items (
    id                 SERIAL PRIMARY KEY,
    run_id             INTEGER NOT NULL REFERENCES prompt_eval_runs(id) ON DELETE CASCADE,
    item_index         INTEGER NOT NULL,
    dataset_version_id INTEGER NOT NULL,
    row_index          INTEGER NOT NULL,
    inputs             JSON NOT NULL DEFAULT '{}',
    created_at         TIMESTAMP DEFAULT now(),
    updated_at         TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_prompt_eval_items_run ON prompt_eval_items(run_id);

CREATE TABLE IF NOT EXISTS prompt_eval_outputs (
    id          SERIAL PRIMARY KEY,
    item_id     INTEGER NOT NULL REFERENCES prompt_eval_items(id) ON DELETE CASCADE,
    arm_id      INTEGER NOT NULL REFERENCES prompt_eval_arms(id),
    output_text TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    error       TEXT,
    latency_ms  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_prompt_eval_outputs_item ON prompt_eval_outputs(item_id);
```

- [ ] **Step 7: 提交**

```bash
git add services/app-server/app/models/prompt_eval.py services/app-server/app/models/__init__.py services/app-server/db/migrations/021_prompt_evals.sql services/app-server/tests/test_prompt_eval.py
git commit -m "$(printf 'feat(app-server): add prompt_eval run/arm/item/output models + migration 021\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 3: 权限 `prompteval:read`/`prompteval:run` + 迁移 022 + 计数

**Files:**
- Modify: `services/app-server/app/bootstrap.py`
- Create: `services/app-server/db/migrations/022_prompteval_perms.sql`
- Modify: `services/app-server/tests/test_bootstrap.py`、`tests/test_migrations_apply.py`
- Test: `services/app-server/tests/test_prompt_eval.py` (APPEND)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompt_eval.py`:

```python
def test_bootstrap_has_prompteval_perms(session_factory):
    from app import bootstrap
    from app.models.rbac import Permission, Role
    from sqlalchemy import select
    db = session_factory()
    bootstrap.seed(db)
    codes = {p.code for p in db.execute(select(Permission)).scalars()}
    assert {"prompteval:read", "prompteval:run"} <= codes
    member = db.execute(select(Role).where(Role.name == "member")).scalar_one()
    viewer = db.execute(select(Role).where(Role.name == "viewer")).scalar_one()
    assert "prompteval:run" in {p.code for p in member.permissions}
    assert "prompteval:read" in {p.code for p in viewer.permissions}
    assert "prompteval:run" not in {p.code for p in viewer.permissions}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_bootstrap_has_prompteval_perms -q`
Expected: FAIL

- [ ] **Step 3: 改 bootstrap.py**

In `services/app-server/app/bootstrap.py`, add to `PERMISSION_CATALOG` after the `("prompt:read", "看 Prompt"), ("prompt:write", "管理 Prompt"),` line:
```python
    ("prompteval:read", "看 Prompt 评测"), ("prompteval:run", "发起 Prompt 评测"),
```
Change `READS` to append `prompteval:read`:
```python
READS = ["dataset:read", "training:read", "model:read", "eval:read", "deploy:read", "badcase:read", "prompt:read", "prompteval:read"]
```
Change `BUSINESS` to append `prompteval:run`:
```python
BUSINESS = READS + ["dataset:write", "training:run", "eval:run", "deploy:write", "model:write", "badcase:annotate", "prompt:write", "prompteval:run"]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_bootstrap_has_prompteval_perms -q`
Expected: PASS

- [ ] **Step 5: 写迁移 022**

Create `services/app-server/db/migrations/022_prompteval_perms.sql`:

```sql
INSERT INTO permissions (code, description) VALUES
  ('prompteval:read', '看 Prompt 评测'),
  ('prompteval:run', '发起 Prompt 评测')
ON CONFLICT (code) DO NOTHING;

-- prompteval:read -> admin, member, viewer
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member', 'viewer') AND p.code = 'prompteval:read'
ON CONFLICT DO NOTHING;

-- prompteval:run -> admin, member
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member') AND p.code = 'prompteval:run'
ON CONFLICT DO NOTHING;
```

- [ ] **Step 6: 更新计数断言(+4 表 / +2 权限)**

In `services/app-server/tests/test_bootstrap.py`, change `== 19` to `== 21`.
In `services/app-server/tests/test_migrations_apply.py`:
- Change `assert ntab == 17 and nperm == 19 and nrole == 4 and sa_perms == 1` to `assert ntab == 21 and nperm == 21 and nrole == 4 and sa_perms == 1`.
- Change the later `assert c.execute(text("SELECT count(*) FROM permissions")).scalar() == 19` to `== 21`.

- [ ] **Step 7: 跑测试确认通过(含真实 PG)**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py tests/test_bootstrap.py tests/test_migrations_apply.py -q`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add services/app-server/app/bootstrap.py services/app-server/db/migrations/022_prompteval_perms.sql services/app-server/tests/test_prompt_eval.py services/app-server/tests/test_bootstrap.py services/app-server/tests/test_migrations_apply.py
git commit -m "$(printf 'feat(app-server): add prompteval:read/prompteval:run permissions + migration 022\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 4: schema

**Files:**
- Create: `services/app-server/app/schemas/prompt_eval.py`
- Test: `services/app-server/tests/test_prompt_eval.py` (APPEND)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompt_eval.py`:

```python
def test_prompt_eval_schema(session_factory):
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm
    from app.schemas.prompt_eval import PromptEvalDetailOut
    db = session_factory()
    run = PromptEvalRun(name="r", eval_type="multi_prompt",
                        prompt_version_ids=[1, 2], model_ids=[3], dataset_version_ids=[4])
    run.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=1, model_id=3, label="A"))
    db.add(run); db.commit(); db.refresh(run)
    out = PromptEvalDetailOut.model_validate(run).model_dump()
    assert out["eval_type"] == "multi_prompt" and out["arms"][0]["label"] == "A"
    assert out["prompt_version_ids"] == [1, 2]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_prompt_eval_schema -q`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 实现 schema**

Create `services/app-server/app/schemas/prompt_eval.py`:

```python
from datetime import datetime
from pydantic import BaseModel


class PromptEvalCreate(BaseModel):
    eval_type: str
    name: str
    prompt_version_ids: list[int] = []
    model_ids: list[int] = []
    dataset_version_ids: list[int] = []


class ArmOut(BaseModel):
    id: int
    arm_index: int
    prompt_version_id: int
    model_id: int
    label: str

    class Config:
        from_attributes = True


class PromptEvalOut(BaseModel):
    id: int
    name: str
    eval_type: str
    status: str
    progress: float
    prompt_version_ids: list[int] = []
    model_ids: list[int] = []
    dataset_version_ids: list[int] = []
    compare_to_version_id: int | None = None
    created_by_name: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class PromptEvalDetailOut(PromptEvalOut):
    arms: list[ArmOut] = []


class OutputOut(BaseModel):
    id: int
    arm_id: int
    output_text: str
    status: str
    error: str | None = None
    latency_ms: int

    class Config:
        from_attributes = True


class ItemOut(BaseModel):
    id: int
    item_index: int
    dataset_version_id: int
    row_index: int
    inputs: dict
    outputs: list[OutputOut] = []

    class Config:
        from_attributes = True
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_prompt_eval_schema -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/app-server/app/schemas/prompt_eval.py services/app-server/tests/test_prompt_eval.py
git commit -m "$(printf 'feat(app-server): add prompt_eval schemas\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 5: `prompt_eval_service`(校验+建模+派发)+ celery dispatch

**Files:**
- Create: `services/app-server/app/services/prompt_eval_service.py`
- Modify: `services/app-server/app/celery_client.py`
- Test: `services/app-server/tests/test_prompt_eval.py` (APPEND)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompt_eval.py`:

```python
def _seed_prompt_and_dataset(db):
    """建一个有 2 个版本的 prompt(参数 name)、一个 llm 模型、一个 prompt 测试集版本(列含 name)。"""
    from app.models.prompt import Prompt, PromptVersion
    from app.models.llm import LlmProvider, LlmModel
    from app.models.dataset import Dataset, DatasetVersion
    p = Prompt(name="问候")
    p.versions.append(PromptVersion(version_no=1, system_prompt="", user_prompt="你好 {{ name }}", params=["name"]))
    p.versions.append(PromptVersion(version_no=2, system_prompt="", user_prompt="hi {{ name }}", params=["name"]))
    db.add(p)
    prov = LlmProvider(name="prov", base_url="u", api_key="k")
    prov.models.append(LlmModel(model_id="gpt-x"))
    db.add(prov)
    ds = Dataset(name="集", kind="prompt", task_type="prompt")
    db.add(ds); db.commit()
    dv = DatasetVersion(dataset_id=ds.id, version_no=1, storage_uri="s3://x/y",
                        row_count=2, checksum="c", note="", stats={"columns": ["name"]})
    db.add(dv); db.commit(); db.refresh(p); db.refresh(prov); db.refresh(dv)
    return p, prov.models[0], dv


def test_service_validation_and_arms(session_factory, monkeypatch):
    import app.services.prompt_eval_service as svc
    monkeypatch.setattr(svc, "send_prompt_eval_task", lambda rid: "celery-1")
    db = session_factory()
    p, model, dv = _seed_prompt_and_dataset(db)
    v1, v2 = p.versions[0].id, p.versions[1].id

    class Body:
        eval_type = "multi_prompt"; name = "r"
        prompt_version_ids = [v1, v2]; model_ids = [model.id]; dataset_version_ids = [dv.id]
    run = svc.create_and_dispatch(db, Body(), created_by=None)
    assert run.eval_type == "multi_prompt" and len(run.arms) == 2 and run.celery_task_id == "celery-1"

    # single_prompt 记录上一版本
    class Body2:
        eval_type = "single_prompt"; name = "r2"
        prompt_version_ids = [v2]; model_ids = [model.id]; dataset_version_ids = [dv.id]
    run2 = svc.create_and_dispatch(db, Body2(), created_by=None)
    assert len(run2.arms) == 1 and run2.compare_to_version_id == v1

    # 数量约束:multi_prompt 只给 1 个 prompt -> ValueError
    import pytest
    class BadCount:
        eval_type = "multi_prompt"; name = "r"
        prompt_version_ids = [v1]; model_ids = [model.id]; dataset_version_ids = [dv.id]
    with pytest.raises(ValueError):
        svc.create_and_dispatch(db, BadCount(), created_by=None)


def test_service_missing_param(session_factory, monkeypatch):
    import app.services.prompt_eval_service as svc
    monkeypatch.setattr(svc, "send_prompt_eval_task", lambda rid: "c")
    from app.models.prompt import Prompt, PromptVersion
    from app.models.llm import LlmProvider, LlmModel
    from app.models.dataset import Dataset, DatasetVersion
    db = session_factory()
    p = Prompt(name="x"); p.versions.append(PromptVersion(version_no=1, system_prompt="",
              user_prompt="{{ city }}", params=["city"]))
    db.add(p)
    prov = LlmProvider(name="pr", base_url="u", api_key="k"); prov.models.append(LlmModel(model_id="m")); db.add(prov)
    ds = Dataset(name="d", kind="prompt", task_type="prompt"); db.add(ds); db.commit()
    dv = DatasetVersion(dataset_id=ds.id, version_no=1, storage_uri="s", row_count=1,
                        checksum="c", note="", stats={"columns": ["name"]})  # 缺 city
    db.add(dv); db.commit(); db.refresh(p); db.refresh(prov); db.refresh(dv)

    class Body:
        eval_type = "single_prompt"; name = "r"
        prompt_version_ids = [p.versions[0].id]; model_ids = [prov.models[0].id]; dataset_version_ids = [dv.id]
    import pytest
    with pytest.raises(ValueError) as ei:
        svc.create_and_dispatch(db, Body(), created_by=None)
    assert "city" in str(ei.value)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_service_validation_and_arms tests/test_prompt_eval.py::test_service_missing_param -q`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 加 celery dispatch**

In `services/app-server/app/celery_client.py`, append:
```python
from modelforge_common.task_names import PROMPT_EVAL_TASK

def send_prompt_eval_task(run_id: int) -> str:
    result = _celery.send_task(PROMPT_EVAL_TASK, args=[run_id])
    return result.id
```

- [ ] **Step 4: 实现 service**

Create `services/app-server/app/services/prompt_eval_service.py`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.prompt import PromptVersion
from app.models.dataset import DatasetVersion
from app.models.llm import LlmModel
from app.models.prompt_eval import PromptEvalRun, PromptEvalArm
from app.celery_client import send_prompt_eval_task   # module-level for monkeypatch


def _check_counts(eval_type: str, pv_ids: list, model_ids: list, dv_ids: list) -> None:
    if len(dv_ids) < 1:
        raise ValueError("至少选择一个测试集")
    if eval_type == "multi_prompt":
        if len(pv_ids) < 2:
            raise ValueError("多 prompt 评测需选择至少 2 个 prompt 版本")
        if len(model_ids) != 1:
            raise ValueError("多 prompt 评测需且仅选 1 个模型")
    elif eval_type == "multi_model":
        if len(model_ids) < 2:
            raise ValueError("多模型评测需选择至少 2 个模型")
        if len(pv_ids) != 1:
            raise ValueError("多模型评测需且仅选 1 个 prompt 版本")
    elif eval_type == "single_prompt":
        if len(pv_ids) != 1 or len(model_ids) != 1:
            raise ValueError("单 prompt 评测需且仅选 1 个 prompt 版本和 1 个模型")
    else:
        raise ValueError(f"未知评测类型:{eval_type}")


def _check_params(db: Session, pv_ids: list, dv_ids: list) -> None:
    needed: set[str] = set()
    for pv_id in pv_ids:
        pv = db.get(PromptVersion, pv_id)
        if pv is None:
            raise ValueError("存在无效的 prompt 版本")
        needed.update(pv.params or [])
    for dv_id in dv_ids:
        dv = db.get(DatasetVersion, dv_id)
        if dv is None:
            raise ValueError("存在无效的测试集版本")
        cols = set((dv.stats or {}).get("columns", []))
        missing = [p for p in needed if p not in cols]
        if missing:
            raise ValueError(f"测试集〈{dv.dataset.name} V{dv.version_no}〉缺少参数 {', '.join(missing)}")


def _label(db: Session, pv_id: int, model_id: int, eval_type: str) -> str:
    if eval_type == "multi_model":
        m = db.get(LlmModel, model_id)
        return m.model_id if m else f"model#{model_id}"
    pv = db.get(PromptVersion, pv_id)
    return f"{pv.prompt.name} V{pv.version_no}" if pv else f"pv#{pv_id}"


def _arm_specs(eval_type: str, pv_ids: list, model_ids: list) -> list[tuple]:
    if eval_type == "multi_prompt":
        return [(i, pv, model_ids[0]) for i, pv in enumerate(pv_ids)]
    if eval_type == "multi_model":
        return [(i, pv_ids[0], m) for i, m in enumerate(model_ids)]
    return [(0, pv_ids[0], model_ids[0])]   # single_prompt


def create_and_dispatch(db: Session, body, created_by=None) -> PromptEvalRun:
    _check_counts(body.eval_type, body.prompt_version_ids, body.model_ids, body.dataset_version_ids)
    _check_params(db, body.prompt_version_ids, body.dataset_version_ids)
    for m_id in body.model_ids:
        if db.get(LlmModel, m_id) is None:
            raise ValueError("存在无效的模型")
    compare_to = None
    if body.eval_type == "single_prompt":
        cur = db.get(PromptVersion, body.prompt_version_ids[0])
        prev = db.execute(select(PromptVersion).where(
            PromptVersion.prompt_id == cur.prompt_id,
            PromptVersion.version_no < cur.version_no
        ).order_by(PromptVersion.version_no.desc())).scalars().first()
        compare_to = prev.id if prev else None
    run = PromptEvalRun(
        name=body.name, eval_type=body.eval_type,
        prompt_version_ids=list(body.prompt_version_ids),
        model_ids=list(body.model_ids),
        dataset_version_ids=list(body.dataset_version_ids),
        compare_to_version_id=compare_to, created_by=created_by)
    for idx, pv_id, m_id in _arm_specs(body.eval_type, body.prompt_version_ids, body.model_ids):
        run.arms.append(PromptEvalArm(arm_index=idx, prompt_version_id=pv_id, model_id=m_id,
                                      label=_label(db, pv_id, m_id, body.eval_type)))
    db.add(run); db.commit(); db.refresh(run)
    run.celery_task_id = send_prompt_eval_task(run.id)
    db.commit(); db.refresh(run)
    return run
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_service_validation_and_arms tests/test_prompt_eval.py::test_service_missing_param -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add services/app-server/app/services/prompt_eval_service.py services/app-server/app/celery_client.py services/app-server/tests/test_prompt_eval.py
git commit -m "$(printf 'feat(app-server): add prompt_eval_service (validate + arms + dispatch)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 6: `/prompt-evals` API + options + 注册

**Files:**
- Create: `services/app-server/app/api/prompt_eval.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_prompt_eval.py` (APPEND)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompt_eval.py`:

```python
from fastapi.testclient import TestClient


def _client(session_factory, codes):
    db = session_factory()
    u = make_user(db, codes=codes, data_scope="all", email="pe@x.com"); db.close()
    from app.main import app
    return TestClient(app), auth_headers(u.id)


def test_prompt_eval_api(session_factory, monkeypatch):
    import app.services.prompt_eval_service as svc
    monkeypatch.setattr(svc, "send_prompt_eval_task", lambda rid: "celery-1")
    # seed via a separate session bound to the same SessionLocal
    from app import db as dbmod
    db = session_factory()
    p, model, dv = _seed_prompt_and_dataset(db)
    v1, v2, mid, dvid = p.versions[0].id, p.versions[1].id, model.id, dv.id
    u = make_user(db, codes=("prompteval:read", "prompteval:run"), data_scope="all", email="pe2@x.com")
    H = auth_headers(u.id); db.close()
    from app.main import app
    c = TestClient(app)
    # options
    opts = c.get("/prompt-evals/options", headers=H).json()
    assert any(o["id"] == v1 for o in opts["prompt_versions"])
    assert any(o["id"] == mid for o in opts["models"])
    assert any(o["version_id"] == dvid for o in opts["prompt_datasets"])
    # create
    r = c.post("/prompt-evals", json={"eval_type": "multi_prompt", "name": "r",
               "prompt_version_ids": [v1, v2], "model_ids": [mid], "dataset_version_ids": [dvid]}, headers=H)
    assert r.status_code == 201
    rid = r.json()["id"]
    assert len(r.json()["arms"]) == 2
    # missing param / bad count -> 422
    assert c.post("/prompt-evals", json={"eval_type": "multi_prompt", "name": "r",
               "prompt_version_ids": [v1], "model_ids": [mid], "dataset_version_ids": [dvid]}, headers=H).status_code == 422
    # list + detail
    assert c.get("/prompt-evals", headers=H).json()[0]["id"] == rid
    assert c.get(f"/prompt-evals/{rid}", headers=H).json()["eval_type"] == "multi_prompt"
    assert c.get(f"/prompt-evals/{rid}/items", headers=H).status_code == 200  # 空 items
    assert c.get("/prompt-evals/99999", headers=H).status_code == 404


def test_prompt_eval_api_requires_perm(session_factory):
    c, H = _client(session_factory, ("dataset:read",))
    assert c.get("/prompt-evals", headers=H).status_code == 403
    assert c.post("/prompt-evals", json={"eval_type": "single_prompt", "name": "r",
               "prompt_version_ids": [1], "model_ids": [1], "dataset_version_ids": [1]}, headers=H).status_code == 403
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_prompt_eval_api tests/test_prompt_eval.py::test_prompt_eval_api_requires_perm -q`
Expected: FAIL(404 路由不存在)

- [ ] **Step 3: 实现路由**

Create `services/app-server/app/api/prompt_eval.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.models.prompt import PromptVersion
from app.models.dataset import Dataset, DatasetVersion
from app.models.llm import LlmModel, LlmProvider
from app.models.prompt_eval import PromptEvalRun, PromptEvalItem
from app.schemas.prompt_eval import PromptEvalCreate, PromptEvalOut, PromptEvalDetailOut, ItemOut
from app.services import prompt_eval_service as svc
from app.pagination import paginate

router = APIRouter(prefix="/prompt-evals", tags=["prompt-evals"])


@router.get("", response_model=list[PromptEvalOut])
def list_runs(response: Response, page: int | None = Query(None, ge=1),
              page_size: int = Query(20, ge=1, le=200),
              _: User = Depends(require("prompteval:read")), db: Session = Depends(get_db)):
    stmt = select(PromptEvalRun).order_by(PromptEvalRun.id.desc())
    return paginate(db, stmt, response, page, page_size)


@router.get("/options")
def eval_options(_: User = Depends(require("prompteval:read")), db: Session = Depends(get_db)):
    pvs = db.execute(select(PromptVersion)
                     .order_by(PromptVersion.prompt_id, PromptVersion.version_no.desc())).scalars().all()
    prompt_versions = [{"id": pv.id, "label": f"{pv.prompt.name} V{pv.version_no}"} for pv in pvs]
    models = [{"id": m.id, "label": f"{m.model_id} · {p.name}"}
              for m, p in db.execute(
                  select(LlmModel, LlmProvider).join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                  .where(LlmProvider.enabled.is_(True))).all()]
    pds = [{"version_id": dv.id, "label": f"{dv.dataset.name} V{dv.version_no}"}
           for dv in db.execute(
               select(DatasetVersion).join(Dataset, Dataset.id == DatasetVersion.dataset_id)
               .where(Dataset.kind == "prompt").order_by(DatasetVersion.id.desc())).scalars().all()]
    return {"prompt_versions": prompt_versions, "models": models, "prompt_datasets": pds}


@router.post("", response_model=PromptEvalDetailOut, status_code=201)
def create_run(body: PromptEvalCreate, user: User = Depends(require("prompteval:run")),
               db: Session = Depends(get_db)):
    try:
        return svc.create_and_dispatch(db, body, created_by=user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/{run_id}", response_model=PromptEvalDetailOut)
def get_run(run_id: int, _: User = Depends(require("prompteval:read")), db: Session = Depends(get_db)):
    run = db.get(PromptEvalRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run


@router.get("/{run_id}/items", response_model=list[ItemOut])
def list_items(run_id: int, response: Response, page: int | None = Query(None, ge=1),
               page_size: int = Query(20, ge=1, le=200),
               _: User = Depends(require("prompteval:read")), db: Session = Depends(get_db)):
    if not db.get(PromptEvalRun, run_id):
        raise HTTPException(404, "run not found")
    stmt = (select(PromptEvalItem).where(PromptEvalItem.run_id == run_id)
            .order_by(PromptEvalItem.item_index))
    return paginate(db, stmt, response, page, page_size)
```

> `/options` 必须声明在 `/{run_id}` 之前(避免被动态段捕获)。

- [ ] **Step 4: 注册路由**

In `services/app-server/app/main.py`, at the END (after the `prompt` router block), add:
```python
from app.api import prompt_eval
app.include_router(prompt_eval.router)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py -q`
Expected: PASS

- [ ] **Step 6: 全量回归**

Run: `cd services/app-server && pytest -q`
Expected: PASS(计数已在 T3 更新)

- [ ] **Step 7: 提交**

```bash
git add services/app-server/app/api/prompt_eval.py services/app-server/app/main.py services/app-server/tests/test_prompt_eval.py
git commit -m "$(printf 'feat(app-server): add /prompt-evals API + options endpoint\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 7: worker 评测引擎

**Files:**
- Modify: `services/train-worker/worker/db.py`
- Create: `services/train-worker/worker/prompt_eval.py`
- Modify: `services/train-worker/worker/tasks.py`
- Test: `services/train-worker/tests/test_prompt_eval_worker.py`

- [ ] **Step 1: 写失败测试**

Create `services/train-worker/tests/test_prompt_eval_worker.py`:

```python
import json
import pandas as pd
from sqlalchemy import create_engine, text


def _setup(engine):
    with engine.begin() as c:
        c.execute(text("CREATE TABLE prompt_eval_runs (id INTEGER PRIMARY KEY, eval_type TEXT, "
                       "status TEXT, progress REAL, error TEXT, dataset_version_ids TEXT)"))
        c.execute(text("CREATE TABLE prompt_eval_arms (id INTEGER PRIMARY KEY, run_id INTEGER, "
                       "arm_index INTEGER, prompt_version_id INTEGER, model_id INTEGER, label TEXT)"))
        c.execute(text("CREATE TABLE prompt_eval_items (id INTEGER PRIMARY KEY, run_id INTEGER, "
                       "item_index INTEGER, dataset_version_id INTEGER, row_index INTEGER, inputs TEXT)"))
        c.execute(text("CREATE TABLE prompt_eval_outputs (id INTEGER PRIMARY KEY, item_id INTEGER, "
                       "arm_id INTEGER, output_text TEXT, status TEXT, error TEXT, latency_ms INTEGER)"))
        c.execute(text("CREATE TABLE prompt_versions (id INTEGER PRIMARY KEY, system_prompt TEXT, user_prompt TEXT)"))
        c.execute(text("CREATE TABLE llm_models (id INTEGER PRIMARY KEY, provider_id INTEGER, model_id TEXT)"))
        c.execute(text("CREATE TABLE llm_providers (id INTEGER PRIMARY KEY, base_url TEXT, api_key TEXT)"))
        c.execute(text("CREATE TABLE dataset_versions (id INTEGER PRIMARY KEY, storage_uri TEXT)"))
        c.execute(text("INSERT INTO llm_providers VALUES (1,'http://u','k')"))
        c.execute(text("INSERT INTO llm_models VALUES (10,1,'gpt-x')"))
        c.execute(text("INSERT INTO prompt_versions VALUES (5,'你是助手','你好 {{ name }}')"))
        c.execute(text("INSERT INTO dataset_versions VALUES (3,'s3://b/k')"))
        c.execute(text("INSERT INTO prompt_eval_runs (id,eval_type,status,progress,dataset_version_ids) "
                       "VALUES (1,'multi_prompt','pending',0,'[3]')"))
        c.execute(text("INSERT INTO prompt_eval_arms VALUES (100,1,0,5,10,'A')"))
        c.execute(text("INSERT INTO prompt_eval_arms VALUES (101,1,1,5,10,'B')"))


def test_run_prompt_eval(tmp_path, monkeypatch):
    from modelforge_common.llm_client import ChatResult, LLMError
    import worker.prompt_eval as pe
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    _setup(eng)
    # 2 行测试集
    monkeypatch.setattr(pe, "read_snapshot", lambda uri: pd.DataFrame({"name": ["小明", "小红"]}))
    calls = []
    def fake_chat(base_url, api_key, model_id, messages, **kw):
        calls.append((model_id, messages))
        if "小红" in messages[-1]["content"]:
            raise LLMError(500, "boom")
        return ChatResult(content="OK:" + messages[-1]["content"], usage=None, raw={})
    monkeypatch.setattr(pe, "llm_chat", fake_chat)

    pe.run_prompt_eval(eng, 1)

    with eng.connect() as c:
        items = c.execute(text("SELECT count(*) FROM prompt_eval_items")).scalar()
        outs = c.execute(text("SELECT count(*) FROM prompt_eval_outputs")).scalar()
        done = c.execute(text("SELECT count(*) FROM prompt_eval_outputs WHERE status='done'")).scalar()
        err = c.execute(text("SELECT count(*) FROM prompt_eval_outputs WHERE status='error'")).scalar()
        run = c.execute(text("SELECT status, progress FROM prompt_eval_runs WHERE id=1")).one()
    assert items == 2 and outs == 4          # 2 行 × 2 臂
    assert done == 2 and err == 2            # 小红的两臂失败
    assert run.status == "succeeded" and run.progress == 1.0
    # system 进了 messages
    assert calls[0][1][0]["role"] == "system"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/train-worker && pytest tests/test_prompt_eval_worker.py -q`
Expected: FAIL(`ModuleNotFoundError: worker.prompt_eval`)

- [ ] **Step 3: 加 worker DB 助手**

Append to `services/train-worker/worker/db.py` (it already imports `text`, `bindparam`, `Engine`, `json`, `JobStatus`, and has `_as_json`):

```python
def set_prompt_eval_status(engine: Engine, run_id: int, status: JobStatus,
                           error: str | None = None) -> None:
    sets = ["status = :s"]
    params = {"s": status.value, "id": run_id}
    if error is not None:
        sets.append("error = :e")
        params["e"] = error
    with engine.begin() as c:
        c.execute(text(f"UPDATE prompt_eval_runs SET {', '.join(sets)} WHERE id = :id"), params)


def set_prompt_eval_progress(engine: Engine, run_id: int, progress: float) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE prompt_eval_runs SET progress = :p WHERE id = :id"),
                  {"p": max(0.0, min(1.0, float(progress))), "id": run_id})


def load_prompt_eval_run(engine: Engine, run_id: int) -> dict:
    with engine.connect() as c:
        run = c.execute(text(
            "SELECT id, eval_type, dataset_version_ids FROM prompt_eval_runs WHERE id = :id"),
            {"id": run_id}).mappings().one()
        arms = c.execute(text(
            "SELECT a.id, a.arm_index, a.prompt_version_id, a.model_id, "
            "pv.system_prompt, pv.user_prompt, lp.base_url, lp.api_key, lm.model_id AS model_str "
            "FROM prompt_eval_arms a "
            "JOIN prompt_versions pv ON pv.id = a.prompt_version_id "
            "JOIN llm_models lm ON lm.id = a.model_id "
            "JOIN llm_providers lp ON lp.id = lm.provider_id "
            "WHERE a.run_id = :id ORDER BY a.arm_index"), {"id": run_id}).mappings().all()
        dv_ids = _as_json(run["dataset_version_ids"]) or []
        datasets = []
        if dv_ids:
            rows = c.execute(text("SELECT id, storage_uri FROM dataset_versions WHERE id IN :ids")
                             .bindparams(bindparam("ids", expanding=True)),
                             {"ids": dv_ids}).mappings().all()
            datasets = [(r["id"], r["storage_uri"]) for r in rows]
    return {"id": run["id"], "eval_type": run["eval_type"],
            "arms": [dict(a) for a in arms], "datasets": datasets}


def insert_eval_item(engine: Engine, run_id: int, item_index: int,
                     dataset_version_id: int, row_index: int, inputs: dict) -> int:
    with engine.begin() as c:
        return c.execute(text(
            "INSERT INTO prompt_eval_items (run_id, item_index, dataset_version_id, row_index, inputs) "
            "VALUES (:r, :i, :d, :ri, :inp) RETURNING id"),
            {"r": run_id, "i": item_index, "d": dataset_version_id, "ri": row_index,
             "inp": json.dumps(inputs, ensure_ascii=False)}).scalar_one()


def insert_eval_output(engine: Engine, item_id: int, arm_id: int) -> int:
    with engine.begin() as c:
        return c.execute(text(
            "INSERT INTO prompt_eval_outputs (item_id, arm_id, status) VALUES (:it, :a, 'pending') "
            "RETURNING id"), {"it": item_id, "a": arm_id}).scalar_one()


def set_output_result(engine: Engine, output_id: int, *, status: str,
                      output_text: str = "", error: str | None = None, latency_ms: int = 0) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE prompt_eval_outputs SET status = :s, output_text = :t, "
                       "error = :e, latency_ms = :l WHERE id = :id"),
                  {"s": status, "t": output_text, "e": error, "l": latency_ms, "id": output_id})
```

- [ ] **Step 4: 实现 worker 引擎**

Create `services/train-worker/worker/prompt_eval.py`:

```python
import time
from modelforge_common.llm_client import chat as llm_chat, LLMError
from modelforge_common.prompt_template import render
from worker.storage import read_snapshot
from worker.db import (JobStatus, load_prompt_eval_run, set_prompt_eval_status,
                       set_prompt_eval_progress, insert_eval_item, insert_eval_output,
                       set_output_result)


def run_prompt_eval(engine, run_id: int) -> None:
    set_prompt_eval_status(engine, run_id, JobStatus.RUNNING)
    set_prompt_eval_progress(engine, run_id, 0.02)
    run = load_prompt_eval_run(engine, run_id)
    arms = run["arms"]

    # 1) 读各测试集快照,展平成 items + 每臂 pending output
    work = []   # [(output_id, arm, inputs)]
    item_index = 0
    for dv_id, uri in run["datasets"]:
        df = read_snapshot(uri)
        cols = list(df.columns)
        for row_index, rec in enumerate(df.to_dict(orient="records")):
            inputs = {k: rec[k] for k in cols}
            item_id = insert_eval_item(engine, run_id, item_index, dv_id, row_index, inputs)
            item_index += 1
            for arm in arms:
                out_id = insert_eval_output(engine, item_id, arm["id"])
                work.append((out_id, arm, inputs))

    # 2) 逐个 output 调 LLM
    total = len(work) or 1
    for i, (out_id, arm, inputs) in enumerate(work):
        t0 = time.monotonic()
        try:
            messages = []
            sys_text = render(arm["system_prompt"] or "", inputs)
            if sys_text.strip():
                messages.append({"role": "system", "content": sys_text})
            messages.append({"role": "user", "content": render(arm["user_prompt"] or "", inputs)})
            res = llm_chat(arm["base_url"], arm["api_key"], arm["model_str"], messages)
            set_output_result(engine, out_id, status="done", output_text=res.content,
                              latency_ms=int((time.monotonic() - t0) * 1000))
        except LLMError as e:
            set_output_result(engine, out_id, status="error", error=e.message,
                              latency_ms=int((time.monotonic() - t0) * 1000))
        set_prompt_eval_progress(engine, run_id, 0.05 + 0.93 * ((i + 1) / total))

    set_prompt_eval_progress(engine, run_id, 1.0)
    set_prompt_eval_status(engine, run_id, JobStatus.SUCCEEDED)
```

- [ ] **Step 5: 注册 Celery task**

In `services/train-worker/worker/tasks.py`, add the import near the top imports:
```python
from modelforge_common.task_names import PROMPT_EVAL_TASK
from worker.prompt_eval import run_prompt_eval
```
And append this task at the END of the file:
```python
@celery_app.task(name=PROMPT_EVAL_TASK, bind=True)
def prompt_eval_task(self, run_id: int):
    engine = build_engine()
    try:
        run_prompt_eval(engine, run_id)
    except Exception as e:
        from worker.db import set_prompt_eval_status
        from modelforge_common.enums import JobStatus
        set_prompt_eval_status(engine, run_id, JobStatus.FAILED, error=str(e))
        raise
    return {"run_id": run_id}
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd services/train-worker && pytest tests/test_prompt_eval_worker.py -q`
Expected: PASS

- [ ] **Step 7: worker 全量回归**

Run: `cd services/train-worker && pytest -q -m "not slow"`
Expected: PASS(无回归)

- [ ] **Step 8: 提交**

```bash
git add services/train-worker/worker/db.py services/train-worker/worker/prompt_eval.py services/train-worker/worker/tasks.py services/train-worker/tests/test_prompt_eval_worker.py
git commit -m "$(printf 'feat(train-worker): add prompt_eval engine (render + LLM batch + outputs)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 8: 前端 API client

**Files:**
- Modify: `frontend/src/api/client.ts`

> 验证 = `npx tsc --noEmit -p tsconfig.app.json`。

- [ ] **Step 1: 加类型与函数**

Append to the END of `frontend/src/api/client.ts`:

```typescript
export type PromptEvalArmRow = { id: number; arm_index: number; prompt_version_id: number; model_id: number; label: string };
export type PromptEval = {
  id: number; name: string; eval_type: string; status: string; progress: number;
  prompt_version_ids: number[]; model_ids: number[]; dataset_version_ids: number[];
  compare_to_version_id: number | null; created_by_name: string | null; created_at: string;
};
export type PromptEvalDetail = PromptEval & { arms: PromptEvalArmRow[] };
export type PromptEvalOutputRow = { id: number; arm_id: number; output_text: string; status: string; error: string | null; latency_ms: number };
export type PromptEvalItem = { id: number; item_index: number; dataset_version_id: number; row_index: number; inputs: Record<string, any>; outputs: PromptEvalOutputRow[] };
export type PromptEvalOptions = {
  prompt_versions: { id: number; label: string }[];
  models: { id: number; label: string }[];
  prompt_datasets: { version_id: number; label: string }[];
};
export const listPromptEvalsPaged = (p: { page: number; page_size: number }) =>
  getPaginated<PromptEval>("/prompt-evals", p);
export const getPromptEvalOptions = () => api.get<PromptEvalOptions>("/prompt-evals/options").then(r => r.data);
export const createPromptEval = (b: { eval_type: string; name: string; prompt_version_ids: number[]; model_ids: number[]; dataset_version_ids: number[] }) =>
  api.post<PromptEvalDetail>("/prompt-evals", b).then(r => r.data);
export const getPromptEval = (id: number) => api.get<PromptEvalDetail>(`/prompt-evals/${id}`).then(r => r.data);
export const listPromptEvalItemsPaged = (id: number, p: { page: number; page_size: number }) =>
  getPaginated<PromptEvalItem>(`/prompt-evals/${id}/items`, p);
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
Expected: no errors

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/client.ts
git commit -m "$(printf 'feat(frontend): add prompt-eval api client\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 9: 前端 Prompt 评测页 + 路由 + 导航

**Files:**
- Create: `frontend/src/pages/PromptEvalsPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`

- [ ] **Step 1: 写页面**

Create `frontend/src/pages/PromptEvalsPage.tsx` with EXACTLY this content:

```tsx
import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { ClipboardCheck, Plus } from "lucide-react";
import {
  listPromptEvalsPaged, createPromptEval, getPromptEvalOptions,
  type PromptEval, type PromptEvalOptions,
} from "../api/client";
import {
  Badge, Button, Drawer, EmptyState, Field, Input, PageHeader, Pagination,
  Select, StatusBadge, TableShell, Creator, CreatedAt,
} from "../ui";
import { toastError } from "../toast";

const TYPE_LABEL: Record<string, string> = {
  multi_prompt: "多 Prompt 盲测", multi_model: "多模型盲测", single_prompt: "单 Prompt 版本对比",
};

function tsName() {
  const d = new Date(), p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function MultiCheck({ options, value, onChange }: {
  options: { id: number; label: string }[]; value: number[]; onChange: (v: number[]) => void;
}) {
  const toggle = (id: number) => onChange(value.includes(id) ? value.filter(x => x !== id) : [...value, id]);
  if (options.length === 0) return <p className="text-[12px] text-slate-400">无可选项</p>;
  return (
    <div className="flex max-h-40 flex-col gap-1 overflow-auto rounded-lg ring-1 ring-slate-200 p-2">
      {options.map(o => (
        <label key={o.id} className="flex items-center gap-2 text-[13px] text-slate-700">
          <input type="checkbox" checked={value.includes(o.id)} onChange={() => toggle(o.id)} />
          {o.label}
        </label>
      ))}
    </div>
  );
}

function NewEvalDrawer({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [opts, setOpts] = useState<PromptEvalOptions | null>(null);
  const [evalType, setEvalType] = useState("multi_prompt");
  const [name, setName] = useState(tsName());
  const [pvs, setPvs] = useState<number[]>([]);
  const [models, setModels] = useState<number[]>([]);
  const [datasets, setDatasets] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { getPromptEvalOptions().then(setOpts).catch(() => toastError("加载选项失败")); }, []);

  const single = <T,>(arr: T[]) => (arr.length ? [arr[0]] : []);
  // 切换类型时按约束收敛已选
  const onType = (t: string) => {
    setEvalType(t);
    if (t === "multi_model") setPvs(p => single(p));
    if (t === "multi_prompt" || t === "single_prompt") setModels(m => single(m));
    if (t === "single_prompt") setPvs(p => single(p));
  };

  const valid = (() => {
    if (datasets.length < 1 || !name.trim()) return false;
    if (evalType === "multi_prompt") return pvs.length >= 2 && models.length === 1;
    if (evalType === "multi_model") return models.length >= 2 && pvs.length === 1;
    return pvs.length === 1 && models.length === 1;   // single_prompt
  })();

  const submit = () => {
    setBusy(true);
    createPromptEval({ eval_type: evalType, name, prompt_version_ids: pvs, model_ids: models, dataset_version_ids: datasets })
      .then(() => { onCreated(); onClose(); })
      .catch(e => toastError(e?.response?.data?.detail ?? "提交失败"))
      .finally(() => setBusy(false));
  };

  const pvOpts = opts?.prompt_versions ?? [];
  const modelOpts = opts?.models ?? [];
  const dsOpts = (opts?.prompt_datasets ?? []).map(d => ({ id: d.version_id, label: d.label }));
  const promptSingle = evalType !== "multi_prompt";
  const modelSingle = evalType !== "multi_model";

  return (
    <Drawer open onClose={onClose} title="新建评测" subtitle="选择评测类型、Prompt 版本、模型与 Prompt 测试集。"
      width="max-w-xl"
      footer={
        <div className="flex items-center justify-end gap-2">
          <Button variant="subtle" disabled={busy} onClick={onClose}>取消</Button>
          <Button variant="primary" disabled={!valid} loading={busy} onClick={submit}>发起评测</Button>
        </div>
      }>
      <div className="flex flex-col gap-4">
        <Field label="评测类型">
          <Select value={evalType} onChange={e => onType(e.target.value)}>
            <option value="multi_prompt">多 Prompt 盲测(多 prompt × 1 模型)</option>
            <option value="multi_model">多模型盲测(1 prompt × 多模型)</option>
            <option value="single_prompt">单 Prompt 版本对比(1 prompt × 1 模型,对比上一版)</option>
          </Select>
        </Field>
        <Field label="名称"><Input value={name} onChange={e => setName(e.target.value)} /></Field>

        <Field label={promptSingle ? "Prompt 版本(选 1)" : "Prompt 版本(多选 ≥2)"}>
          {promptSingle ? (
            <Select value={pvs[0] ?? ""} onChange={e => setPvs(e.target.value ? [Number(e.target.value)] : [])}>
              <option value="">选择 Prompt 版本…</option>
              {pvOpts.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
            </Select>
          ) : <MultiCheck options={pvOpts} value={pvs} onChange={setPvs} />}
        </Field>

        <Field label={modelSingle ? "模型(选 1)" : "模型(多选 ≥2)"}>
          {modelSingle ? (
            <Select value={models[0] ?? ""} onChange={e => setModels(e.target.value ? [Number(e.target.value)] : [])}>
              <option value="">选择模型…</option>
              {modelOpts.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
            </Select>
          ) : <MultiCheck options={modelOpts} value={models} onChange={setModels} />}
        </Field>

        <Field label="Prompt 测试集(多选)">
          <MultiCheck options={dsOpts} value={datasets} onChange={setDatasets} />
        </Field>
      </div>
    </Drawer>
  );
}

export function PromptEvalsPage() {
  const [items, setItems] = useState<PromptEval[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [open, setOpen] = useState(false);

  const reload = () => listPromptEvalsPaged({ page, page_size: pageSize })
    .then(res => { setItems(res.items); setTotal(res.total); });
  useEffect(() => {
    setLoading(true); reload().finally(() => setLoading(false));
    const t = setInterval(reload, 3000); return () => clearInterval(t);
  }, [page, pageSize]);

  return (
    <>
      <PageHeader title="Prompt 评测"
        subtitle="发起多 Prompt / 多模型 / 单 Prompt 版本对比评测;跑完进入工作台盲测评估。"
        actions={<Button variant="primary" onClick={() => setOpen(true)}><Plus size={16} /> 新建评测</Button>} />

      <TableShell loading={loading} empty={items.length === 0}
        head={<><th>名称</th><th>类型</th><th>状态</th><th>进度</th><th>创建者</th><th className="w-36">创建时间</th></>}>
        {items.length === 0 ? (
          <EmptyState icon={<ClipboardCheck size={22} />} title="还没有评测" hint="新建一个 Prompt 评测。" />
        ) : items.map(r => (
          <tr key={r.id}>
            <td className="font-medium text-slate-800">{r.name}</td>
            <td><Badge tone="gray">{TYPE_LABEL[r.eval_type] ?? r.eval_type}</Badge></td>
            <td><StatusBadge status={r.status} /></td>
            <td>
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full bg-brand-500" style={{ width: `${Math.round(r.progress * 100)}%` }} />
                </div>
                <span className="text-[12px] text-slate-500">{Math.round(r.progress * 100)}%</span>
              </div>
            </td>
            <td><Creator name={r.created_by_name} /></td>
            <td><CreatedAt at={r.created_at} /></td>
          </tr>
        ))}
      </TableShell>
      <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />

      {open && <NewEvalDrawer onClose={() => setOpen(false)} onCreated={reload} />}
    </>
  );
}
```

- [ ] **Step 2: 注册路由**

In `frontend/src/App.tsx`, add an import alongside the other page imports:
```tsx
import { PromptEvalsPage } from "./pages/PromptEvalsPage";
```
And add a route line after the `/prompts` branch:
```tsx
  else if (path === "/prompt-evals") page = <PromptEvalsPage />;
```

- [ ] **Step 3: 加导航项**

In `frontend/src/components/AppShell.tsx`: add `ClipboardCheck` to the `lucide-react` import; in the `NAV` array, add after the prompts entry:
```tsx
  { href: "/prompt-evals", label: "Prompt 评测", icon: <ClipboardCheck size={18} />, perm: "prompteval:read", match: p => p.startsWith("/prompt-evals") },
```

- [ ] **Step 4: 类型检查 + 构建**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm run build`
Expected: no type errors; build succeeds.

If a `ui` prop differs, open `frontend/src/ui.tsx` and adjust minimally (verify `StatusBadge`, `Select`, `Drawer width`, `Badge tone` are as used elsewhere — DeployPage/EvalPage use `StatusBadge` + `Select`).

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/PromptEvalsPage.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx
git commit -m "$(printf 'feat(frontend): add Prompt 评测 page (3 eval types + run list)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## 收尾验证(全部任务后)

- [ ] `cd services/common && pytest -q`、`cd services/app-server && pytest -q`(含真实 PG:21 表 / 21 权限)、`cd services/train-worker && pytest -q -m "not slow"` 全绿。
- [ ] 前端 `npx tsc --noEmit -p tsconfig.app.json` 与 `npm run build` 通过。
- [ ] 手动冒烟:重启 app-server(迁移 021/022)+ worker → admin 登录 →「Prompt 评测」可见 → 新建一个多 prompt 评测(选 ≥2 prompt 版本 + 1 模型 + ≥1 prompt 测试集)→ 进度跑到 100%、状态 succeeded → run 详情/items 有各臂输出。
- [ ] 参数不匹配的测试集被拒并提示缺哪个参数;无 `prompteval:read` 看不到入口、API 403。

---

## 自审记录(对照 spec)

- **Spec 覆盖**:render+task_name(T1)、4 模型+迁移 021(T2)、权限+迁移 022+计数(T3)、schema(T4)、service 校验/arms/派发(T5)、API+options(T6)、worker 引擎(T7)、前端 client(T8)、评测页(T9)。verdict/统计/AI 评估按 spec 留给 C2/D。
- **占位符**:无;每步给完整代码与命令。
- **类型一致**:`PROMPT_EVAL_TASK`(T1)→ celery_client send(T5)→ worker task(T7)一致;service `_arm_specs`/`_check_counts`(T5)↔ API(T6)↔ schema 字段(T4)一致;worker `load_prompt_eval_run` 返回的 arm 字段(`system_prompt/user_prompt/base_url/api_key/model_str`)↔ `run_prompt_eval` 使用一致;`insert_eval_item/insert_eval_output/set_output_result/set_prompt_eval_*`(T7 db)↔ `run_prompt_eval`(T7)一致;前端 `PromptEval*` 类型(T8)↔ 评测页(T9)与 `PromptEvalOptions`(options 端点 T6)一致(`prompt_datasets[].version_id`)。
- **计数**:T3 统一 test_bootstrap→21、test_migrations_apply→21 表/21 权限,T6 全量回归确认。
```
