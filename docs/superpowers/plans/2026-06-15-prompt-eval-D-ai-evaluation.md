# 子项目 D:AI 自动评估 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 用一个评判大模型对某评测的 item 自动判优(多臂选最佳 / 单 prompt 判好坏),把 AI 判定与人工 verdict 并存写回,展示来源与 AI 推理;评判系统指令在设置页可配。

**Architecture:** 给 `prompt_eval_items` 加并行 AI 列(迁移 025)+ 新建通用 `app_settings` 表存评判指令(默认值在代码);触发 API 派发 Celery worker,worker 逐条 pending item 调评判模型、强制 JSON 解析、写 AI 列;前端设置页编辑指令 + 列表/工作台触发与展示。

**Tech Stack:** FastAPI + SQLAlchemy + 编号迁移;Celery worker(原始 SQL)+ `llm_client`;pytest;React + TS。

**Spec:** [`docs/superpowers/specs/2026-06-15-prompt-eval-D-ai-evaluation-design.md`](../specs/2026-06-15-prompt-eval-D-ai-evaluation-design.md)

**铁律(`CLAUDE.md`)**:改 `app/models/**` 必配编号迁移;app-server 与 train-worker 互不 import(worker 用原始 SQL + 共享 `modelforge_common`);macOS worker `--pool=solo`。当前最新迁移 `024`,新增 `025`。提交以 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` 结尾。

## 文件结构

| 文件 | 职责 | 任务 |
|---|---|---|
| `services/app-server/app/models/prompt_eval.py` | PromptEvalItem 加 AI 列 | T1 |
| `services/app-server/app/models/setting.py` + `models/__init__.py` | `AppSetting` | T1 |
| `services/app-server/db/migrations/025_ai_evaluation.sql` | AI 列 + app_settings 表 | T1 |
| `services/app-server/tests/test_migrations_apply.py` | ntab 21→22 | T1 |
| `services/common/modelforge_common/task_names.py` | `PROMPT_AI_EVAL_TASK` | T2 |
| `services/app-server/app/ai_eval_defaults.py` | `DEFAULT_AI_EVAL_PROMPT` | T2 |
| `services/app-server/app/services/ai_eval_service.py` | get/set prompt + dispatch | T2 |
| `services/app-server/app/celery_client.py` | `send_prompt_ai_eval_task` | T2 |
| `services/app-server/app/schemas/prompt_eval.py` + `schemas/setting.py` | ItemOut AI 字段 + AiEvaluateIn + 设置 schema | T3 |
| `services/app-server/app/api/settings.py` + `api/prompt_eval.py` + `main.py` | 设置 API + 触发 API + ItemOut 构造 | T3 |
| `services/app-server/tests/test_ai_eval.py` | service/API 测试 | T2,T3 |
| `services/train-worker/worker/prompt_ai_eval.py` + `worker/db.py` + `worker/tasks.py` | worker 评判 | T4 |
| `services/train-worker/tests/test_prompt_ai_eval_worker.py` | worker 测试 | T4 |
| `frontend/src/api/client.ts` | client | T5 |
| `frontend/src/pages/SettingsPage.tsx` + `PromptEvalsPage.tsx` | 设置区 + 触发 | T6 |
| `frontend/src/pages/PromptEvalWorkbench.tsx` | AI 结果展示 | T7 |

---

### Task 1: AI 列 + AppSetting 模型 + 迁移 025

**Files:**
- Modify: `services/app-server/app/models/prompt_eval.py`
- Create: `services/app-server/app/models/setting.py`
- Modify: `services/app-server/app/models/__init__.py`
- Create: `services/app-server/db/migrations/025_ai_evaluation.sql`
- Modify: `services/app-server/tests/test_migrations_apply.py`
- Test: `services/app-server/tests/test_ai_eval.py`

- [ ] **Step 1: 写失败测试**

Create `services/app-server/tests/test_ai_eval.py`:

```python
from tests.conftest import make_user, auth_headers


def test_ai_columns_and_setting(session_factory):
    from datetime import datetime, timezone
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem
    from app.models.setting import AppSetting
    db = session_factory()
    run = PromptEvalRun(name="r", eval_type="multi_prompt",
                        prompt_version_ids=[1], model_ids=[2], dataset_version_ids=[3])
    run.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=1, model_id=2, label="A"))
    db.add(run); db.commit(); db.refresh(run)
    it = PromptEvalItem(run_id=run.id, item_index=0, dataset_version_id=3, row_index=0, inputs={})
    it.ai_winner_arm_id = run.arms[0].id
    it.ai_model_id = 2
    it.ai_reasoning = "because A is best"
    it.ai_evaluated_at = datetime.now(timezone.utc)
    db.add(it); db.commit(); db.refresh(it)
    assert it.ai_winner_arm_id == run.arms[0].id and it.ai_all_bad is False and it.ai_is_good is None
    assert it.ai_reasoning == "because A is best"
    s = AppSetting(key="ai_eval_prompt", value="judge!"); db.add(s); db.commit()
    assert db.get(AppSetting, "ai_eval_prompt").value == "judge!"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_ai_eval.py::test_ai_columns_and_setting -q`
Expected: FAIL(no `ai_winner_arm_id` / `ModuleNotFoundError: app.models.setting`)

- [ ] **Step 3: 加 AI 列**

In `services/app-server/app/models/prompt_eval.py`, in the `PromptEvalItem` class, after the C2 verdict columns (after `evaluated_at`) and before the `outputs` relationship, add:
```python
    ai_winner_arm_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_eval_arms.id"), nullable=True)
    ai_all_bad: Mapped[bool] = mapped_column(default=False)
    ai_is_good: Mapped[bool | None] = mapped_column(nullable=True)
    ai_model_id: Mapped[int | None] = mapped_column(ForeignKey("llm_models.id"), nullable=True)
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_evaluated_at: Mapped[datetime | None] = mapped_column(nullable=True)
```
(`Text`, `datetime`, `ForeignKey` are already imported in this file.)

- [ ] **Step 4: 加 AppSetting 模型**

Create `services/app-server/app/models/setting.py`:
```python
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
```
In `services/app-server/app/models/__init__.py`, add an import after the prompt_eval import:
```python
from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem, PromptEvalOutput
from app.models.setting import AppSetting
```
And add `"AppSetting"` to `__all__` (after `"PromptEvalOutput",`).

- [ ] **Step 5: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_ai_eval.py::test_ai_columns_and_setting -q`
Expected: PASS

- [ ] **Step 6: 写迁移 025**

Create `services/app-server/db/migrations/025_ai_evaluation.sql`:
```sql
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ai_winner_arm_id INTEGER REFERENCES prompt_eval_arms(id);
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ai_all_bad BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ai_is_good BOOLEAN;
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ai_model_id INTEGER REFERENCES llm_models(id);
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ai_reasoning TEXT;
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ai_evaluated_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

- [ ] **Step 7: 更新表计数(+1 表:app_settings;权限不变)**

In `services/app-server/tests/test_migrations_apply.py`, change `assert ntab == 21 and nperm == 22 and nrole == 4 and sa_perms == 1` to `assert ntab == 22 and nperm == 22 and nrole == 4 and sa_perms == 1` (only `ntab` 21→22; `nperm` stays 22; the later permission re-check stays `== 22`). Do NOT change `test_bootstrap.py` (permission count unchanged).

- [ ] **Step 8: 跑测试确认通过(含真实 PG)**

Run: `cd services/app-server && pytest tests/test_ai_eval.py tests/test_migrations_apply.py -q`
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add services/app-server/app/models/prompt_eval.py services/app-server/app/models/setting.py services/app-server/app/models/__init__.py services/app-server/db/migrations/025_ai_evaluation.sql services/app-server/tests/test_migrations_apply.py services/app-server/tests/test_ai_eval.py
git commit -m "$(printf 'feat(app-server): add AI verdict columns + app_settings table + migration 025\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project D (AI auto-eval). The AI verdict columns are PARALLEL to C2's human verdict columns (both coexist on an item — user wants both results kept). `app_settings` is a generic key-value table whose first use is the configurable AI-judge system instruction. IRON RULE: model change ships migration 025 (idempotent `ADD COLUMN IF NOT EXISTS` + `CREATE TABLE IF NOT EXISTS`). 025 adds ONE new table (app_settings) → table count 21→22; no new permission. Tests use SQLite + `create_all`. The test file `test_ai_eval.py` is APPENDED to by later tasks.

---

### Task 2: task name + 默认指令 + ai_eval_service + 派发

**Files:**
- Modify: `services/common/modelforge_common/task_names.py`
- Create: `services/app-server/app/ai_eval_defaults.py`
- Create: `services/app-server/app/services/ai_eval_service.py`
- Modify: `services/app-server/app/celery_client.py`
- Test: `services/app-server/tests/test_ai_eval.py` (APPEND)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_ai_eval.py`:

```python
def test_ai_eval_service_prompt_and_dispatch(session_factory, monkeypatch):
    import app.services.ai_eval_service as svc
    from app.ai_eval_defaults import DEFAULT_AI_EVAL_PROMPT
    db = session_factory()
    # GET 默认
    assert svc.get_prompt(db) == DEFAULT_AI_EVAL_PROMPT
    # SET 后 GET 返回新值
    svc.set_prompt(db, "我的评判指令")
    assert svc.get_prompt(db) == "我的评判指令"
    # SET 再次(upsert,不报错)
    svc.set_prompt(db, "v2")
    assert svc.get_prompt(db) == "v2"

    # dispatch:有效模型派发,无效模型 ValueError
    from app.models.llm import LlmProvider, LlmModel
    from app.models.prompt_eval import PromptEvalRun
    prov = LlmProvider(name="p", base_url="u", api_key="k"); prov.models.append(LlmModel(model_id="m"))
    db.add(prov)
    run = PromptEvalRun(name="r", eval_type="multi_prompt", prompt_version_ids=[1],
                        model_ids=[1], dataset_version_ids=[1]); db.add(run); db.commit()
    db.refresh(prov); db.refresh(run)
    sent = {}
    monkeypatch.setattr(svc, "send_prompt_ai_eval_task",
                        lambda rid, mid, jp: sent.update(rid=rid, mid=mid, jp=jp) or "celery-ai-1")
    svc.dispatch(db, run.id, prov.models[0].id)
    assert sent["rid"] == run.id and sent["mid"] == prov.models[0].id and sent["jp"] == "v2"
    import pytest
    with pytest.raises(ValueError):
        svc.dispatch(db, run.id, 999999)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_ai_eval.py::test_ai_eval_service_prompt_and_dispatch -q`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: 加 task name**

In `services/common/modelforge_common/task_names.py`, add:
```python
PROMPT_AI_EVAL_TASK = "modelforge.prompt_ai_eval"
```

- [ ] **Step 4: 加默认指令**

Create `services/app-server/app/ai_eval_defaults.py`:
```python
DEFAULT_AI_EVAL_PROMPT = (
    "你是严格的评测助手。下面会给出一个任务的输入,以及一个或多个候选回答。\n"
    "- 若有多个候选:选出质量最好的一个;如果都不好,判定为都一样坏。\n"
    "- 若只有一个候选:判定它好还是坏。\n"
    "只输出 JSON,不要任何多余文字:\n"
    "  多个候选时:{\"winner\": 序号}(序号从 1 开始)或 {\"all_bad\": true}\n"
    "  单个候选时:{\"good\": true} 或 {\"good\": false}"
)
```

- [ ] **Step 5: 加 celery 派发**

In `services/app-server/app/celery_client.py`, append:
```python
from modelforge_common.task_names import PROMPT_AI_EVAL_TASK

def send_prompt_ai_eval_task(run_id: int, model_id: int, judge_prompt: str) -> str:
    result = _celery.send_task(PROMPT_AI_EVAL_TASK, args=[run_id, model_id, judge_prompt])
    return result.id
```

- [ ] **Step 6: 实现 ai_eval_service**

Create `services/app-server/app/services/ai_eval_service.py`:
```python
from sqlalchemy.orm import Session
from app.models.setting import AppSetting
from app.models.llm import LlmModel
from app.models.prompt_eval import PromptEvalRun
from app.ai_eval_defaults import DEFAULT_AI_EVAL_PROMPT
from app.celery_client import send_prompt_ai_eval_task   # module-level for monkeypatch

_KEY = "ai_eval_prompt"


def get_prompt(db: Session) -> str:
    s = db.get(AppSetting, _KEY)
    return s.value if s and s.value else DEFAULT_AI_EVAL_PROMPT


def set_prompt(db: Session, value: str) -> None:
    s = db.get(AppSetting, _KEY)
    if s is None:
        s = AppSetting(key=_KEY, value=value)
        db.add(s)
    else:
        s.value = value
    db.commit()


def dispatch(db: Session, run_id: int, model_id: int) -> None:
    if db.get(PromptEvalRun, run_id) is None:
        raise ValueError("评测不存在")
    if db.get(LlmModel, model_id) is None:
        raise ValueError("评判模型无效")
    send_prompt_ai_eval_task(run_id, model_id, get_prompt(db))
```

- [ ] **Step 7: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_ai_eval.py::test_ai_eval_service_prompt_and_dispatch -q`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add services/common/modelforge_common/task_names.py services/app-server/app/ai_eval_defaults.py services/app-server/app/services/ai_eval_service.py services/app-server/app/celery_client.py services/app-server/tests/test_ai_eval.py
git commit -m "$(printf 'feat(app-server): add ai_eval_service (prompt get/set + dispatch) + default prompt\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project D. `ai_eval_service` resolves the judge system instruction (stored `app_settings['ai_eval_prompt']` or `DEFAULT_AI_EVAL_PROMPT` if unset/empty), and `dispatch` validates run+model then sends the Celery task with the RESOLVED prompt as an arg (so the worker doesn't need DB access to settings or the default). `send_prompt_ai_eval_task` is imported module-level so tests can monkeypatch (mirrors `prompt_eval_service`). APPEND to `test_ai_eval.py`.

---

### Task 3: schemas + 设置 API + 触发 API + ItemOut 构造

**Files:**
- Modify: `services/app-server/app/schemas/prompt_eval.py`
- Create: `services/app-server/app/schemas/setting.py`
- Create: `services/app-server/app/api/settings.py`
- Modify: `services/app-server/app/api/prompt_eval.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_ai_eval.py` (APPEND)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_ai_eval.py`:

```python
from fastapi.testclient import TestClient


def test_settings_and_trigger_api(session_factory, monkeypatch):
    import app.services.ai_eval_service as svc
    from app.models.llm import LlmProvider, LlmModel
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem
    db = session_factory()
    prov = LlmProvider(name="p", base_url="u", api_key="k"); prov.models.append(LlmModel(model_id="m"))
    db.add(prov)
    run = PromptEvalRun(name="r", eval_type="multi_prompt", prompt_version_ids=[1],
                        model_ids=[1], dataset_version_ids=[1])
    run.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=1, model_id=1, label="A"))
    db.add(run); db.commit(); db.refresh(prov); db.refresh(run)
    it = PromptEvalItem(run_id=run.id, item_index=0, dataset_version_id=1, row_index=0, inputs={})
    db.add(it); db.commit()
    mid, rid, iid = prov.models[0].id, run.id, it.id
    admin = make_user(db, codes=("llm:manage", "prompteval:read", "prompteval:annotate"), data_scope="all", email="ad@x.com")
    H = auth_headers(admin.id); db.close()
    from app.main import app
    monkeypatch.setattr(svc, "send_prompt_ai_eval_task", lambda rid, mid, jp: "celery-ai-1")
    c = TestClient(app)
    # 设置 GET 默认含 JSON 字样
    g = c.get("/settings/ai-eval-prompt", headers=H).json()
    assert "JSON" in g["value"]
    # PUT 后 GET 返回新值
    assert c.put("/settings/ai-eval-prompt", json={"value": "改过了"}, headers=H).status_code == 200
    assert c.get("/settings/ai-eval-prompt", headers=H).json()["value"] == "改过了"
    # 触发:有效
    assert c.post(f"/prompt-evals/{rid}/ai-evaluate", json={"model_id": mid}, headers=H).status_code == 200
    # 触发:无效模型 422
    assert c.post(f"/prompt-evals/{rid}/ai-evaluate", json={"model_id": 999999}, headers=H).status_code == 422
    # items 带 AI 字段(默认 null)
    items = c.get(f"/prompt-evals/{rid}/items", headers=H).json()
    assert items[0]["ai_winner_arm_id"] is None and "ai_reasoning" in items[0]


def test_settings_requires_perm(session_factory):
    c, H = (lambda: (None, None))()  # placeholder
    db = session_factory()
    u = make_user(db, codes=("prompteval:read",), data_scope="all", email="np@x.com")
    H = auth_headers(u.id); db.close()
    from app.main import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    assert c.get("/settings/ai-eval-prompt", headers=H).status_code == 403
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_ai_eval.py::test_settings_and_trigger_api tests/test_ai_eval.py::test_settings_requires_perm -q`
Expected: FAIL(404 / 缺路由)

- [ ] **Step 3: 加 schema**

In `services/app-server/app/schemas/prompt_eval.py`, REPLACE the `ItemOut` class with (adds AI fields after the C2 verdict fields):
```python
class ItemOut(BaseModel):
    id: int
    item_index: int
    dataset_version_id: int
    row_index: int
    inputs: dict
    outputs: list[OutputOut] = []
    winner_arm_id: int | None = None
    all_bad: bool = False
    is_good: bool | None = None
    annotated_by_name: str | None = None
    evaluated_at: datetime | None = None
    ai_winner_arm_id: int | None = None
    ai_all_bad: bool = False
    ai_is_good: bool | None = None
    ai_model_id: int | None = None
    ai_reasoning: str | None = None
    ai_evaluated_at: datetime | None = None

    class Config:
        from_attributes = True
```
And add an `AiEvaluateIn` class at the END of the file:
```python
class AiEvaluateIn(BaseModel):
    model_id: int
```
Create `services/app-server/app/schemas/setting.py`:
```python
from pydantic import BaseModel


class AiEvalPromptOut(BaseModel):
    value: str


class AiEvalPromptIn(BaseModel):
    value: str = ""
```

- [ ] **Step 4: 加设置 API**

Create `services/app-server/app/api/settings.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.schemas.setting import AiEvalPromptOut, AiEvalPromptIn
from app.services import ai_eval_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/ai-eval-prompt", response_model=AiEvalPromptOut)
def get_ai_eval_prompt(_: User = Depends(require("llm:manage")), db: Session = Depends(get_db)):
    return AiEvalPromptOut(value=ai_eval_service.get_prompt(db))


@router.put("/ai-eval-prompt", response_model=AiEvalPromptOut)
def put_ai_eval_prompt(body: AiEvalPromptIn, _: User = Depends(require("llm:manage")),
                       db: Session = Depends(get_db)):
    ai_eval_service.set_prompt(db, body.value)
    return AiEvalPromptOut(value=ai_eval_service.get_prompt(db))
```

- [ ] **Step 5: 加触发 API + ItemOut AI 字段构造**

In `services/app-server/app/api/prompt_eval.py`:

(a) add imports (only the missing ones):
```python
from app.schemas.prompt_eval import AiEvaluateIn
from app.services import ai_eval_service
```

(b) In BOTH places that construct `ItemOut(...)` (in `list_items` and in `submit_verdict`), add the 6 AI fields to the constructor call (after `evaluated_at=...`):
```python
            ai_winner_arm_id=it.ai_winner_arm_id, ai_all_bad=it.ai_all_bad, ai_is_good=it.ai_is_good,
            ai_model_id=it.ai_model_id, ai_reasoning=it.ai_reasoning, ai_evaluated_at=it.ai_evaluated_at,
```
(in `submit_verdict` the loop variable is `item` not `it` — use `item.ai_winner_arm_id` etc. there).

(c) add this route after `submit_verdict`:
```python
@router.post("/{run_id}/ai-evaluate")
def ai_evaluate(run_id: int, body: AiEvaluateIn,
                _: User = Depends(require("prompteval:annotate")), db: Session = Depends(get_db)):
    try:
        ai_eval_service.dispatch(db, run_id, body.model_id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"dispatched": True}
```

- [ ] **Step 6: 注册设置路由**

In `services/app-server/app/main.py`, at the END (after the `prompt_eval` router block), add:
```python
from app.api import settings as settings_api
app.include_router(settings_api.router)
```

- [ ] **Step 7: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_ai_eval.py -q`
Expected: PASS

- [ ] **Step 8: 全量回归**

Run: `cd services/app-server && pytest -q`
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add services/app-server/app/schemas/prompt_eval.py services/app-server/app/schemas/setting.py services/app-server/app/api/settings.py services/app-server/app/api/prompt_eval.py services/app-server/app/main.py services/app-server/tests/test_ai_eval.py
git commit -m "$(printf 'feat(app-server): AI-eval settings + trigger endpoints + ItemOut AI fields\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project D. Settings endpoints (gated `llm:manage`, lives under the 设置页) read/write the judge prompt; the trigger endpoint (gated `prompteval:annotate`) validates + dispatches. `ItemOut` now carries the AI verdict fields so the frontend can show AI results — they must be added to BOTH explicit `ItemOut(...)` constructions in `api/prompt_eval.py` (list_items uses `it`, submit_verdict uses `item`). `main.py` already registered the `prompt_eval` router (C1); add the new `settings` router. APPEND tests only.

---

### Task 4: worker 评判引擎

**Files:**
- Modify: `services/train-worker/worker/db.py`
- Create: `services/train-worker/worker/prompt_ai_eval.py`
- Modify: `services/train-worker/worker/tasks.py`
- Test: `services/train-worker/tests/test_prompt_ai_eval_worker.py`

- [ ] **Step 1: 写失败测试**

Create `services/train-worker/tests/test_prompt_ai_eval_worker.py`:

```python
from sqlalchemy import create_engine, text


def _setup(engine):
    with engine.begin() as c:
        c.execute(text("CREATE TABLE prompt_eval_runs (id INTEGER PRIMARY KEY, eval_type TEXT)"))
        c.execute(text("CREATE TABLE prompt_eval_arms (id INTEGER PRIMARY KEY, run_id INTEGER, arm_index INTEGER)"))
        c.execute(text("CREATE TABLE prompt_eval_items (id INTEGER PRIMARY KEY, run_id INTEGER, inputs TEXT, "
                       "ai_winner_arm_id INTEGER, ai_all_bad INTEGER, ai_is_good INTEGER, ai_model_id INTEGER, "
                       "ai_reasoning TEXT, ai_evaluated_at TIMESTAMP)"))
        c.execute(text("CREATE TABLE prompt_eval_outputs (id INTEGER PRIMARY KEY, item_id INTEGER, arm_id INTEGER, output_text TEXT)"))
        c.execute(text("CREATE TABLE llm_models (id INTEGER PRIMARY KEY, provider_id INTEGER, model_id TEXT)"))
        c.execute(text("CREATE TABLE llm_providers (id INTEGER PRIMARY KEY, base_url TEXT, api_key TEXT)"))
        c.execute(text("INSERT INTO llm_providers VALUES (1,'http://u','k')"))
        c.execute(text("INSERT INTO llm_models VALUES (9,1,'judge-x')"))
        c.execute(text("INSERT INTO prompt_eval_runs VALUES (1,'multi_prompt')"))
        c.execute(text("INSERT INTO prompt_eval_arms VALUES (10,1,0)"))
        c.execute(text("INSERT INTO prompt_eval_arms VALUES (11,1,1)"))
        c.execute(text("INSERT INTO prompt_eval_items (id,run_id,inputs) VALUES (100,1,'{\"q\":\"x\"}')"))
        c.execute(text("INSERT INTO prompt_eval_outputs VALUES (1000,100,10,'ans A')"))
        c.execute(text("INSERT INTO prompt_eval_outputs VALUES (1001,100,11,'ans B')"))


def test_run_prompt_ai_eval(tmp_path, monkeypatch):
    from modelforge_common.llm_client import ChatResult
    import worker.prompt_ai_eval as pe
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    _setup(eng)
    monkeypatch.setattr(pe, "llm_chat",
                        lambda *a, **k: ChatResult(content='评判结果:{"winner": 2}', usage=None, raw={}))
    pe.run_prompt_ai_eval(eng, run_id=1, model_id=9, judge_prompt="judge")
    with eng.connect() as c:
        row = c.execute(text("SELECT ai_winner_arm_id, ai_model_id, ai_reasoning, ai_evaluated_at "
                             "FROM prompt_eval_items WHERE id=100")).one()
    assert row.ai_winner_arm_id == 11      # winner 2 -> arms[1] (arm_index 1) -> id 11
    assert row.ai_model_id == 9 and row.ai_evaluated_at is not None and "winner" in row.ai_reasoning


def test_ai_eval_bad_json_does_not_abort(tmp_path, monkeypatch):
    from modelforge_common.llm_client import ChatResult
    import worker.prompt_ai_eval as pe
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    _setup(eng)
    monkeypatch.setattr(pe, "llm_chat", lambda *a, **k: ChatResult(content="不是 JSON", usage=None, raw={}))
    pe.run_prompt_ai_eval(eng, run_id=1, model_id=9, judge_prompt="judge")
    with eng.connect() as c:
        row = c.execute(text("SELECT ai_winner_arm_id, ai_reasoning, ai_evaluated_at "
                             "FROM prompt_eval_items WHERE id=100")).one()
    assert row.ai_winner_arm_id is None and row.ai_evaluated_at is not None and row.ai_reasoning == "不是 JSON"


def test_ai_eval_only_pending(tmp_path, monkeypatch):
    from modelforge_common.llm_client import ChatResult
    import worker.prompt_ai_eval as pe
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    _setup(eng)
    with eng.begin() as c:  # 标记已 AI 评
        c.execute(text("UPDATE prompt_eval_items SET ai_evaluated_at='2020-01-01' WHERE id=100"))
    called = []
    monkeypatch.setattr(pe, "llm_chat", lambda *a, **k: called.append(1) or ChatResult(content="{}", usage=None, raw={}))
    pe.run_prompt_ai_eval(eng, run_id=1, model_id=9, judge_prompt="judge")
    assert called == []   # 已 AI 评的不再处理
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/train-worker && pytest tests/test_prompt_ai_eval_worker.py -q`
Expected: FAIL(`ModuleNotFoundError: worker.prompt_ai_eval`)

- [ ] **Step 3: 加 worker DB 助手**

Append to `services/train-worker/worker/db.py`:
```python
def load_ai_eval_context(engine: Engine, run_id: int, model_id: int) -> dict:
    with engine.connect() as c:
        run = c.execute(text("SELECT eval_type FROM prompt_eval_runs WHERE id = :id"),
                        {"id": run_id}).mappings().one()
        model = c.execute(text(
            "SELECT lm.model_id AS model_str, lp.base_url, lp.api_key "
            "FROM llm_models lm JOIN llm_providers lp ON lp.id = lm.provider_id "
            "WHERE lm.id = :id"), {"id": model_id}).mappings().one()
        arms = c.execute(text("SELECT id, arm_index FROM prompt_eval_arms "
                              "WHERE run_id = :id ORDER BY arm_index"), {"id": run_id}).mappings().all()
    return {"eval_type": run["eval_type"], "base_url": model["base_url"],
            "api_key": model["api_key"], "model_str": model["model_str"],
            "arms": [dict(a) for a in arms]}


def pending_ai_items(engine: Engine, run_id: int) -> list[dict]:
    with engine.connect() as c:
        items = c.execute(text("SELECT id, inputs FROM prompt_eval_items "
                               "WHERE run_id = :id AND ai_evaluated_at IS NULL ORDER BY id"),
                          {"id": run_id}).mappings().all()
        out = []
        for it in items:
            outs = c.execute(text("SELECT arm_id, output_text FROM prompt_eval_outputs WHERE item_id = :i"),
                             {"i": it["id"]}).mappings().all()
            out.append({"id": it["id"], "inputs": _as_json(it["inputs"]) or {},
                        "outputs": [dict(o) for o in outs]})
    return out


def set_ai_verdict(engine: Engine, item_id: int, *, ai_winner_arm_id, ai_all_bad, ai_is_good,
                   ai_model_id, ai_reasoning, evaluated_at) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE prompt_eval_items SET ai_winner_arm_id = :w, ai_all_bad = :ab, "
                       "ai_is_good = :ig, ai_model_id = :m, ai_reasoning = :r, ai_evaluated_at = :at "
                       "WHERE id = :id"),
                  {"w": ai_winner_arm_id, "ab": ai_all_bad, "ig": ai_is_good, "m": ai_model_id,
                   "r": ai_reasoning, "at": evaluated_at, "id": item_id})
```

- [ ] **Step 4: 实现 worker 引擎**

Create `services/train-worker/worker/prompt_ai_eval.py`:
```python
import json
import re
from datetime import datetime, timezone
from modelforge_common.llm_client import chat as llm_chat, LLMError
from worker.db import load_ai_eval_context, pending_ai_items, set_ai_verdict

_JSON_RE = re.compile(r"\{.*\}", re.S)


def _parse(content: str) -> dict | None:
    m = _JSON_RE.search(content or "")
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
        return v if isinstance(v, dict) else None
    except (ValueError, TypeError):
        return None


def _build_user(eval_type: str, inputs: dict, candidates: list[str]) -> str:
    lines = ["【任务输入】", json.dumps(inputs, ensure_ascii=False), "【候选回答】"]
    if eval_type == "single_prompt":
        lines.append(candidates[0] if candidates else "")
    else:
        for i, c in enumerate(candidates, 1):
            lines.append(f"候选{i}: {c}")
    return "\n".join(lines)


def run_prompt_ai_eval(engine, run_id: int, model_id: int, judge_prompt: str) -> None:
    ctx = load_ai_eval_context(engine, run_id, model_id)
    eval_type = ctx["eval_type"]
    arms = ctx["arms"]   # already ordered by arm_index
    for item in pending_ai_items(engine, run_id):
        by_arm = {o["arm_id"]: o["output_text"] for o in item["outputs"]}
        candidates = [by_arm.get(a["id"], "") for a in arms]
        verdict = {"ai_winner_arm_id": None, "ai_all_bad": False, "ai_is_good": None,
                   "ai_model_id": model_id, "ai_reasoning": ""}
        try:
            res = llm_chat(ctx["base_url"], ctx["api_key"], ctx["model_str"],
                           [{"role": "system", "content": judge_prompt},
                            {"role": "user", "content": _build_user(eval_type, item["inputs"], candidates)}])
            verdict["ai_reasoning"] = res.content
            parsed = _parse(res.content)
            if parsed:
                if eval_type == "single_prompt":
                    if isinstance(parsed.get("good"), bool):
                        verdict["ai_is_good"] = parsed["good"]
                else:
                    if parsed.get("all_bad") is True:
                        verdict["ai_all_bad"] = True
                    elif isinstance(parsed.get("winner"), int) and 1 <= parsed["winner"] <= len(arms):
                        verdict["ai_winner_arm_id"] = arms[parsed["winner"] - 1]["id"]
        except LLMError as e:
            verdict["ai_reasoning"] = f"调用失败:{e.message}"
        set_ai_verdict(engine, item["id"], evaluated_at=datetime.now(timezone.utc), **verdict)
```

- [ ] **Step 5: 注册 Celery task**

In `services/train-worker/worker/tasks.py`, add imports near the top:
```python
from modelforge_common.task_names import PROMPT_AI_EVAL_TASK
from worker.prompt_ai_eval import run_prompt_ai_eval
```
And append at the END:
```python
@celery_app.task(name=PROMPT_AI_EVAL_TASK, bind=True)
def prompt_ai_eval_task(self, run_id: int, model_id: int, judge_prompt: str):
    engine = build_engine()
    run_prompt_ai_eval(engine, run_id, model_id, judge_prompt)
    return {"run_id": run_id}
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd services/train-worker && pytest tests/test_prompt_ai_eval_worker.py -q`
Expected: PASS

- [ ] **Step 7: worker 全量回归**

Run: `cd services/train-worker && pytest -q -m "not slow"`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add services/train-worker/worker/db.py services/train-worker/worker/prompt_ai_eval.py services/train-worker/worker/tasks.py services/train-worker/tests/test_prompt_ai_eval_worker.py
git commit -m "$(printf 'feat(train-worker): add prompt_ai_eval engine (LLM judge + JSON parse)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project D. The worker AI-judges each pending item (`ai_evaluated_at IS NULL`): loads the run eval_type + judge-model creds + arms (raw SQL), builds a system(judge_prompt)+user(inputs+candidates) message, calls `llm_client.chat`, extracts the first `{...}` and `json.loads` it, maps `winner` (1-based) → `arms[winner-1].id`, writes the AI columns + reasoning + timestamp. Any LLMError / non-JSON / out-of-range winner → leaves the verdict columns null but still records reasoning + `ai_evaluated_at` (so it isn't reprocessed) and continues. Worker is decoupled (raw SQL + `modelforge_common`). The Celery task receives the already-resolved `judge_prompt` from app-server (no settings DB access needed).

---

### Task 5: 前端 API client

**Files:**
- Modify: `frontend/src/api/client.ts`

> 验证 = `npx tsc --noEmit -p tsconfig.app.json`。

- [ ] **Step 1: 改 ItemOut 类型 + 加 settings/trigger 函数**

In `frontend/src/api/client.ts`:

(a) Find the existing `export type PromptEvalItem = {...}` and REPLACE it with (adds AI fields):
```typescript
export type PromptEvalItem = {
  id: number; item_index: number; dataset_version_id: number; row_index: number;
  inputs: Record<string, any>; outputs: PromptEvalOutputRow[];
  winner_arm_id: number | null; all_bad: boolean; is_good: boolean | null;
  annotated_by_name: string | null; evaluated_at: string | null;
  ai_winner_arm_id: number | null; ai_all_bad: boolean; ai_is_good: boolean | null;
  ai_model_id: number | null; ai_reasoning: string | null; ai_evaluated_at: string | null;
};
```

(b) Append at the END of the file:
```typescript
export const getAiEvalPrompt = () => api.get<{ value: string }>("/settings/ai-eval-prompt").then(r => r.data.value);
export const setAiEvalPrompt = (value: string) => api.put<{ value: string }>("/settings/ai-eval-prompt", { value }).then(r => r.data.value);
export const triggerAiEval = (runId: number, modelId: number) =>
  api.post<{ dispatched: boolean }>(`/prompt-evals/${runId}/ai-evaluate`, { model_id: modelId }).then(r => r.data);
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
Expected: no errors

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/client.ts
git commit -m "$(printf 'feat(frontend): add ai-eval prompt settings + trigger client + ItemOut AI fields\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project D. `PromptEvalItem` gains the AI verdict fields the backend now returns. `getAiEvalPrompt`/`setAiEvalPrompt` back the settings-page editor; `triggerAiEval` posts the AI-eval trigger. `api`, `PromptEvalOutputRow` already exist. Stage ONLY `client.ts`.

---

### Task 6: 设置页 AI Prompt 区块 + 列表触发

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/pages/PromptEvalsPage.tsx`

- [ ] **Step 1: 设置页加 AI Prompt 区块**

In `frontend/src/pages/SettingsPage.tsx`:
(a) add imports:
```tsx
import { getAiEvalPrompt, setAiEvalPrompt } from "../api/client";
import { toastSuccess } from "../toast";
```
(`toastError`, `useState`, `useEffect`, `Button` should already be imported — verify; add `useEffect`/`toastSuccess` if missing.)
(b) Add an `AiEvalPromptCard` component at the END of the file:
```tsx
function AiEvalPromptCard() {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { getAiEvalPrompt().then(setValue).catch(() => {}); }, []);
  const save = () => {
    setBusy(true);
    setAiEvalPrompt(value).then(() => toastSuccess("已保存")).catch(() => toastError("保存失败")).finally(() => setBusy(false));
  };
  return (
    <div className="mt-8 rounded-2xl bg-white p-6 ring-1 ring-slate-200/70">
      <div className="mb-1 text-[15px] font-semibold text-slate-800">AI 评估 Prompt</div>
      <p className="mb-3 text-[12.5px] text-slate-500">AI 自动评估时给评判模型的系统指令。要求模型只输出 JSON(多候选 {"{"}"winner": 序号{"}"} / {"{"}"all_bad": true{"}"};单候选 {"{"}"good": true/false{"}"})。</p>
      <textarea value={value} onChange={e => setValue(e.target.value)} rows={8}
        className="w-full rounded-lg bg-white px-3 py-2 text-sm text-slate-900 ring-1 ring-slate-200 outline-none focus:ring-2 focus:ring-brand-500 font-mono" />
      <div className="mt-3 flex justify-end"><Button variant="primary" loading={busy} onClick={save}>保存</Button></div>
    </div>
  );
}
```
(c) Render `<AiEvalPromptCard />` inside the `SettingsPage` return, after the providers `TableShell`/`Pagination` block (just before the closing fragment/element). Find where the providers table + pagination end and add `<AiEvalPromptCard />` right after them.

- [ ] **Step 2: 列表加「AI 评估」触发**

In `frontend/src/pages/PromptEvalsPage.tsx`:
(a) extend imports — add `triggerAiEval` and `Sparkles` icon, and `Select` if needed:
```tsx
import { ClipboardCheck, Plus, PencilLine, BarChart3, Sparkles } from "lucide-react";
```
add `triggerAiEval` to the `../api/client` import list, and ensure `Select` is in the `../ui` import.
(b) add state in `PromptEvalsPage`:
```tsx
  const [aiRun, setAiRun] = useState<PromptEval | null>(null);
```
(c) in the succeeded-row actions cell (next to 评估/统计), add:
```tsx
                  <Button size="sm" variant="subtle" onClick={() => setAiRun(r)}><Sparkles size={13} /> AI 评估</Button>
```
(d) add the AI-eval picker drawer render before the closing `</>` (after the stats drawer line):
```tsx
      {aiRun && <AiEvalDrawer run={aiRun} onClose={() => setAiRun(null)} />}
```
(e) add the `AiEvalDrawer` component at the END of the file (it loads models from `getPromptEvalOptions`):
```tsx
function AiEvalDrawer({ run, onClose }: { run: PromptEval; onClose: () => void }) {
  const [models, setModels] = useState<{ id: number; label: string }[]>([]);
  const [mid, setMid] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { getPromptEvalOptions().then(o => setModels(o.models)).catch(() => toastError("加载模型失败")); }, []);
  const go = () => {
    setBusy(true);
    triggerAiEval(run.id, Number(mid))
      .then(() => { toastSuccess("已发起 AI 评估,稍后刷新查看结果"); onClose(); })
      .catch(e => toastError(e?.response?.data?.detail ?? "发起失败"))
      .finally(() => setBusy(false));
  };
  return (
    <Drawer open onClose={onClose} title="AI 自动评估" subtitle={`用评判模型对「${run.name}」未 AI 评的数据自动判优。`} width="max-w-md"
      footer={<div className="flex justify-end gap-2"><Button variant="subtle" disabled={busy} onClick={onClose}>取消</Button><Button variant="primary" disabled={!mid} loading={busy} onClick={go}><Sparkles size={15} /> 开始</Button></div>}>
      <Field label="评判模型">
        <Select value={mid} onChange={e => setMid(e.target.value)}>
          <option value="">选择评判模型…</option>
          {models.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
        </Select>
      </Field>
    </Drawer>
  );
}
```
(ensure `toastSuccess`, `Field`, `Drawer` are imported in this file — add to the existing imports if missing.)

- [ ] **Step 3: 类型检查 + 构建**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm run build`
Expected: no type errors; build succeeds. If a `ui` prop differs, open `frontend/src/ui.tsx` and adjust minimally.

- [ ] **Step 4: 提交**

```bash
git add frontend/src/pages/SettingsPage.tsx frontend/src/pages/PromptEvalsPage.tsx
git commit -m "$(printf 'feat(frontend): AI-eval prompt editor on settings + AI-eval trigger on eval list\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project D. The settings page (A's `SettingsPage`) gains an editable AI-judge prompt card. The Prompt 评测 list gets an 「AI 评估」 button per succeeded run that opens a small drawer to pick a judge model (from `getPromptEvalOptions().models`) and POSTs the trigger. Stage ONLY the 2 files.

---

### Task 7: 工作台展示 AI 评估结果

**Files:**
- Modify: `frontend/src/pages/PromptEvalWorkbench.tsx`

- [ ] **Step 1: 加 AI 结果展示**

In `frontend/src/pages/PromptEvalWorkbench.tsx`, in the right pane (where the current item `cur` is rendered), AFTER the verdict buttons row, add an AI-result block. Find the `{cur.evaluated_at && <span ...>已评 ...</span>}` area / the end of the verdict button row, and after that closing `</div>` add:
```tsx
              {cur.ai_evaluated_at && (
                <div className="rounded-xl bg-violet-50 p-3 ring-1 ring-violet-100">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="rounded bg-violet-600 px-1.5 py-0.5 text-[11px] font-medium text-white">AI 评估</span>
                    <span className="text-[12.5px] text-slate-600">
                      {single
                        ? (cur.ai_is_good === true ? "判定:好" : cur.ai_is_good === false ? "判定:坏" : "未判定")
                        : (cur.ai_all_bad ? "判定:都一样坏"
                            : cur.ai_winner_arm_id != null
                              ? `选了 ${LETTERS[cur.outputs.findIndex(o => o.arm_id === cur.ai_winner_arm_id)] ?? "?"}`
                              : "未判定")}
                    </span>
                  </div>
                  {cur.ai_reasoning && <pre className="whitespace-pre-wrap text-[12px] text-slate-500">{cur.ai_reasoning}</pre>}
                </div>
              )}
```
(`LETTERS`, `single`, `cur` are already in scope in this component.)

Also add an AI marker in the left list next to the human-eval check — find the `{i.evaluated_at && <Check ... />}` in the item-list button and add after it:
```tsx
                    {i.ai_evaluated_at && <span className="ml-1 rounded bg-violet-100 px-1 text-[10px] text-violet-600">AI</span>}
```

- [ ] **Step 2: 类型检查 + 构建**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/PromptEvalWorkbench.tsx
git commit -m "$(printf 'feat(frontend): show AI verdict + reasoning + source in eval workbench\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project D final task. The workbench right pane shows the AI verdict (which candidate letter the AI picked, or good/bad, or 都一样坏) + the AI's raw reasoning in a distinct violet block, alongside the human verdict. The left item list gets an "AI" marker when an item has been AI-evaluated. The blind shuffle from C2 still applies to the display order, and `cur.ai_winner_arm_id` is mapped back to the displayed letter via `cur.outputs.findIndex(o => o.arm_id === ...)`. Stage ONLY this file.

---

## 收尾验证(全部任务后)

- [ ] `cd services/app-server && pytest -q`(含真实 PG:22 表 / 22 权限)、`cd services/train-worker && pytest -q -m "not slow"`、前端 `tsc` + `build` 全绿。
- [ ] 手动冒烟:重启 app-server(迁移 025)+ worker → 设置页改 AI 评估 Prompt → 对一个 succeeded 评测点「AI 评估」选模型 → worker 异步把未 AI 评的 item 逐条判优 → 工作台看到 AI 评估块(选择 + 推理)与人工 verdict 并存。
- [ ] 无 `llm:manage` 不能读写 AI Prompt(403);无 `prompteval:annotate` 不能触发(403)。

---

## 自审记录(对照 spec)

- **Spec 覆盖**:AI 列 + app_settings + 迁移 025(T1)、task 名 + 默认指令 + service + 派发(T2)、schema + 设置 API + 触发 API + ItemOut AI 字段(T3)、worker 评判引擎(T4)、前端 client(T5)、设置区 + 触发(T6)、工作台 AI 展示(T7)。
- **占位符**:无;每步完整代码与命令(T4 的 `pending_ai_items` 明确用简化版、删 `_has_item_index`)。
- **类型一致**:`PROMPT_AI_EVAL_TASK`(T2)→ celery send(T2)→ worker task(T4)一致;`ai_eval_service.dispatch` 派发 `(run_id, model_id, judge_prompt)`(T2)↔ worker `run_prompt_ai_eval(run_id, model_id, judge_prompt)`(T4)一致;worker `load_ai_eval_context` 返回字段(`base_url/api_key/model_str/arms`)↔ `run_prompt_ai_eval` 使用一致;`set_ai_verdict` 参数(T4 db)↔ 调用一致;ItemOut AI 字段(T3)↔ 前端 `PromptEvalItem`(T5)↔ 工作台展示(T7)一致;winner 序号(1基)→ `arms[winner-1].id` 与前端 `findIndex(arm_id)` 映射一致。
- **计数**:T1 把 test_migrations_apply ntab→22(nperm/test_bootstrap 不变),T3 全量回归确认。
```
