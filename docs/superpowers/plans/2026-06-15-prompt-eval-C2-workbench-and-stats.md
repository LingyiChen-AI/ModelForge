# 子项目 C2:盲测人工评估工作台 + 每轮统计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 让评估人对 C1 跑出的待评估输出做盲测人工评估(多臂选谁更好/单 prompt 好坏),verdict 落库,并按需算出每轮统计(各 arm 胜率与最优;单 prompt 好率与变好/变坏率)。

**Architecture:** 给 C1 的 `prompt_eval_items` 加 verdict 列(迁移 023);后端取 items 时按 `random.Random(item.id)` 打乱各臂输出做盲测匿名;verdict PATCH 落库;stats 实时聚合;前端两栏工作台 + 统计抽屉 + C1 列表入口。无 worker。

**Tech Stack:** FastAPI + SQLAlchemy + 编号 SQL 迁移;pytest;React + TS + Vite。

**Spec:** [`docs/superpowers/specs/2026-06-15-prompt-eval-C2-workbench-and-stats-design.md`](../specs/2026-06-15-prompt-eval-C2-workbench-and-stats-design.md)

**铁律(`CLAUDE.md`)**:改 `app/models/**` 必配编号迁移;改 RBAC 时 bootstrap + 迁移一起改。当前最新迁移 `022`,新增 `023`(加列)、`024`(权限)。提交以 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` 结尾。

## 文件结构

| 文件 | 职责 | 任务 |
|---|---|---|
| `services/app-server/app/models/prompt_eval.py` | `PromptEvalItem` 加 verdict 列 + annotator | T1 |
| `services/app-server/db/migrations/023_prompt_eval_verdict.sql` | 加列 | T1 |
| `services/app-server/app/bootstrap.py` + `024_prompteval_annotate_perm.sql` | `prompteval:annotate` | T2 |
| `tests/test_bootstrap.py`、`tests/test_migrations_apply.py` | 计数(21 表 / 22 权限) | T2 |
| `services/app-server/app/schemas/prompt_eval.py` | `VerdictIn` + `ItemOut` 加 verdict 字段 | T3 |
| `services/app-server/app/services/prompt_eval_service.py` | `submit_verdict` | T3 |
| `services/app-server/app/services/prompt_eval_stats.py` | `stats` | T3 |
| `services/app-server/app/api/prompt_eval.py` | items 扩展 + verdict + stats | T4 |
| `services/app-server/tests/test_prompt_eval.py` | service/API 测试 | T1,T3,T4 |
| `frontend/src/api/client.ts` | client | T5 |
| `frontend/src/pages/PromptEvalWorkbench.tsx` + `App.tsx` | 工作台 | T6 |
| `frontend/src/pages/PromptEvalsPage.tsx` | 统计抽屉 + 入口按钮 | T7 |

---

### Task 1: verdict 列 + 迁移 023

**Files:**
- Modify: `services/app-server/app/models/prompt_eval.py`
- Create: `services/app-server/db/migrations/023_prompt_eval_verdict.sql`
- Test: `services/app-server/tests/test_prompt_eval.py` (APPEND)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompt_eval.py`:

```python
def test_item_verdict_columns(session_factory):
    from datetime import datetime, timezone
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem
    from app.models.user import User
    from app.models.rbac import Role
    db = session_factory()
    role = Role(name="r-v", data_scope="all"); db.add(role); db.commit()
    u = User(name="judge", email="j@x.com", role_id=role.id); db.add(u); db.commit()
    run = PromptEvalRun(name="r", eval_type="multi_prompt",
                        prompt_version_ids=[1], model_ids=[2], dataset_version_ids=[3])
    run.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=1, model_id=2, label="A"))
    db.add(run); db.commit(); db.refresh(run)
    it = PromptEvalItem(run_id=run.id, item_index=0, dataset_version_id=3, row_index=0, inputs={})
    it.winner_arm_id = run.arms[0].id
    it.evaluated_by = u.id
    it.evaluated_at = datetime.now(timezone.utc)
    db.add(it); db.commit(); db.refresh(it)
    assert it.winner_arm_id == run.arms[0].id and it.all_bad is False and it.is_good is None
    assert it.annotated_by_name == "judge"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_item_verdict_columns -q`
Expected: FAIL(`AttributeError`/无 `winner_arm_id`)

- [ ] **Step 3: 加列到模型**

In `services/app-server/app/models/prompt_eval.py`, in the `PromptEvalItem` class, after the `inputs` column and before the `outputs` relationship, add:
```python
    winner_arm_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_eval_arms.id"), nullable=True)
    all_bad: Mapped[bool] = mapped_column(default=False)
    is_good: Mapped[bool | None] = mapped_column(nullable=True)
    evaluated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    evaluated_at: Mapped["datetime | None"] = mapped_column(nullable=True)
```
Add the `annotator` relationship + property at the END of the `PromptEvalItem` class body (after the `outputs` relationship):
```python
    annotator: Mapped["User | None"] = relationship(  # type: ignore  # noqa: F821
        "User", lazy="selectin", viewonly=True, foreign_keys=[evaluated_by])

    @property
    def annotated_by_name(self) -> str | None:
        return self.annotator.name if self.annotator else None
```
At the top of the file, ensure `datetime` is importable for the annotation — add this import line near the top:
```python
from datetime import datetime
```
(The `"datetime | None"` Mapped annotation is a forward-ref string so it resolves at mapper-config time; the import makes it concrete.)

- [ ] **Step 4: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_item_verdict_columns -q`
Expected: PASS

- [ ] **Step 5: 写迁移 023**

Create `services/app-server/db/migrations/023_prompt_eval_verdict.sql`:

```sql
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS winner_arm_id INTEGER REFERENCES prompt_eval_arms(id);
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS all_bad BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS is_good BOOLEAN;
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS evaluated_by INTEGER REFERENCES users(id);
ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMP;
```

- [ ] **Step 6: 提交**

```bash
git add services/app-server/app/models/prompt_eval.py services/app-server/db/migrations/023_prompt_eval_verdict.sql services/app-server/tests/test_prompt_eval.py
git commit -m "$(printf 'feat(app-server): add verdict columns to prompt_eval_items + migration 023\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project C2. These columns hold the human blind-eval result on each item: `winner_arm_id`/`all_bad` for multi-arm runs, `is_good` for single_prompt, plus who/when. The `annotator`/`annotated_by_name` pattern mirrors `app/models/badcase.py` exactly. IRON RULE: model change ships migration 023 (here `ALTER TABLE ADD COLUMN IF NOT EXISTS`, idempotent — these add COLUMNS so the table count is unchanged). Tests use SQLite + `create_all`. APPEND to `test_prompt_eval.py`.

---

### Task 2: 权限 `prompteval:annotate` + 迁移 024 + 计数

**Files:**
- Modify: `services/app-server/app/bootstrap.py`
- Create: `services/app-server/db/migrations/024_prompteval_annotate_perm.sql`
- Modify: `services/app-server/tests/test_bootstrap.py`、`tests/test_migrations_apply.py`
- Test: `services/app-server/tests/test_prompt_eval.py` (APPEND)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompt_eval.py`:

```python
def test_bootstrap_has_prompteval_annotate(session_factory):
    from app import bootstrap
    from app.models.rbac import Permission, Role
    from sqlalchemy import select
    db = session_factory()
    bootstrap.seed(db)
    assert db.execute(select(Permission).where(Permission.code == "prompteval:annotate")).scalar_one_or_none()
    member = db.execute(select(Role).where(Role.name == "member")).scalar_one()
    viewer = db.execute(select(Role).where(Role.name == "viewer")).scalar_one()
    assert "prompteval:annotate" in {p.code for p in member.permissions}
    assert "prompteval:annotate" not in {p.code for p in viewer.permissions}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_bootstrap_has_prompteval_annotate -q`
Expected: FAIL

- [ ] **Step 3: 改 bootstrap.py**

In `services/app-server/app/bootstrap.py`, add to `PERMISSION_CATALOG` immediately after the `("prompteval:read", "看 Prompt 评测"), ("prompteval:run", "发起 Prompt 评测"),` line:
```python
    ("prompteval:annotate", "标注 Prompt 评估"),
```
Change `BUSINESS` to append `prompteval:annotate` at the end of its added list:
```python
BUSINESS = READS + ["dataset:write", "training:run", "eval:run", "deploy:write", "model:write", "badcase:annotate", "prompt:write", "prompteval:run", "prompteval:annotate"]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_bootstrap_has_prompteval_annotate -q`
Expected: PASS

- [ ] **Step 5: 写迁移 024**

Create `services/app-server/db/migrations/024_prompteval_annotate_perm.sql`:

```sql
INSERT INTO permissions (code, description) VALUES
  ('prompteval:annotate', '标注 Prompt 评估')
ON CONFLICT (code) DO NOTHING;

-- prompteval:annotate -> admin, member
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name IN ('admin', 'member') AND p.code = 'prompteval:annotate'
ON CONFLICT DO NOTHING;
```

- [ ] **Step 6: 更新计数断言(+1 权限,表不变)**

This sub-project's migration 023 only ADDS COLUMNS (table count unchanged = 21); 024 adds 1 permission (21 → 22).

In `services/app-server/tests/test_bootstrap.py`, change the permission-count assertion `== 21` to `== 22`.

In `services/app-server/tests/test_migrations_apply.py`:
- Change `assert ntab == 21 and nperm == 21 and nrole == 4 and sa_perms == 1` to `assert ntab == 21 and nperm == 22 and nrole == 4 and sa_perms == 1` (ntab STAYS 21).
- Change the later re-check `assert c.execute(text("SELECT count(*) FROM permissions")).scalar() == 21` to `== 22`.

- [ ] **Step 7: 跑测试确认通过(含真实 PG)**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py tests/test_bootstrap.py tests/test_migrations_apply.py -q`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add services/app-server/app/bootstrap.py services/app-server/db/migrations/024_prompteval_annotate_perm.sql services/app-server/tests/test_prompt_eval.py services/app-server/tests/test_bootstrap.py services/app-server/tests/test_migrations_apply.py
git commit -m "$(printf 'feat(app-server): add prompteval:annotate permission + migration 024\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project C2. `prompteval:annotate` gates the verdict-submit endpoint. IRON RULE: bootstrap + migration together; `superadmin` has `*`. Counts: 023 added columns (no new table → 21 stays), 024 adds the perm (→22). Mirror `db/migrations/022_prompteval_perms.sql`. APPEND to `test_prompt_eval.py`.

---

### Task 3: schemas + verdict service + stats service

**Files:**
- Modify: `services/app-server/app/schemas/prompt_eval.py`
- Modify: `services/app-server/app/services/prompt_eval_service.py`
- Create: `services/app-server/app/services/prompt_eval_stats.py`
- Test: `services/app-server/tests/test_prompt_eval.py` (APPEND)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompt_eval.py`:

```python
def _seed_eval_run(db, eval_type, n_arms=2):
    """建一个 run + n_arms 个 arm + 一个 item(无 output),返回 (run, [arm...], item)。"""
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem
    run = PromptEvalRun(name="r", eval_type=eval_type,
                        prompt_version_ids=[1], model_ids=[2], dataset_version_ids=[3])
    for i in range(n_arms):
        run.arms.append(PromptEvalArm(arm_index=i, prompt_version_id=1, model_id=2, label=f"L{i}"))
    db.add(run); db.commit(); db.refresh(run)
    it = PromptEvalItem(run_id=run.id, item_index=0, dataset_version_id=3, row_index=0, inputs={})
    db.add(it); db.commit(); db.refresh(it)
    return run, run.arms, it


def test_submit_verdict_multi_and_single(session_factory):
    import app.services.prompt_eval_service as svc
    db = session_factory()
    # 多臂:winner
    run, arms, it = _seed_eval_run(db, "multi_prompt", 2)

    class WIN: winner_arm_id = None; all_bad = False; is_good = None
    WIN.winner_arm_id = arms[1].id
    out = svc.submit_verdict(db, it.id, WIN, user_id=None)
    assert out.winner_arm_id == arms[1].id and out.evaluated_at is not None and out.all_bad is False
    # 多臂:all_bad
    class AB: winner_arm_id = None; all_bad = True; is_good = None
    it2_run, it2_arms, it2 = _seed_eval_run(db, "multi_prompt", 2)
    out2 = svc.submit_verdict(db, it2.id, AB, user_id=None)
    assert out2.all_bad is True and out2.winner_arm_id is None
    # 多臂:都没给 -> ValueError
    import pytest
    class NONE: winner_arm_id = None; all_bad = False; is_good = None
    _, _, it3 = _seed_eval_run(db, "multi_prompt", 2)
    with pytest.raises(ValueError):
        svc.submit_verdict(db, it3.id, NONE, user_id=None)
    # 多臂:winner 不属于该 run -> ValueError
    class BADARM: winner_arm_id = 999999; all_bad = False; is_good = None
    _, _, it4 = _seed_eval_run(db, "multi_prompt", 2)
    with pytest.raises(ValueError):
        svc.submit_verdict(db, it4.id, BADARM, user_id=None)
    # 单 prompt:is_good
    class GOOD: winner_arm_id = None; all_bad = False; is_good = True
    _, _, its = _seed_eval_run(db, "single_prompt", 1)
    outs = svc.submit_verdict(db, its.id, GOOD, user_id=None)
    assert outs.is_good is True and outs.evaluated_at is not None
    # 单 prompt 缺 is_good -> ValueError
    class NOGOOD: winner_arm_id = None; all_bad = False; is_good = None
    _, _, its2 = _seed_eval_run(db, "single_prompt", 1)
    with pytest.raises(ValueError):
        svc.submit_verdict(db, its2.id, NOGOOD, user_id=None)
    # 不存在 item
    assert svc.submit_verdict(db, 999999, GOOD, user_id=None) is None


def test_stats_multi_and_single(session_factory):
    from datetime import datetime, timezone
    from app.models.prompt_eval import PromptEvalItem, PromptEvalArm, PromptEvalRun
    from app.services import prompt_eval_stats as st
    db = session_factory()
    run, arms, it = _seed_eval_run(db, "multi_prompt", 3)
    # 3 个已评 item:arm0 赢 2,arm1 赢 1
    it.winner_arm_id = arms[0].id; it.evaluated_at = datetime.now(timezone.utc)
    for w in (arms[0].id, arms[1].id):
        x = PromptEvalItem(run_id=run.id, item_index=99, dataset_version_id=3, row_index=0,
                           inputs={}, winner_arm_id=w, evaluated_at=datetime.now(timezone.utc))
        db.add(x)
    db.commit()
    s = st.stats(db, run.id)
    by = {a["arm_id"]: a for a in s["arms"]}
    assert by[arms[0].id]["wins"] == 2 and by[arms[1].id]["wins"] == 1
    assert s["best_arm_id"] == arms[0].id and s["evaluated"] == 3

    # 单 prompt + 变好/变坏:上一版本一个已评 run,本 run 一个已评 item
    from app.models.prompt import Prompt, PromptVersion
    p = Prompt(name="pp")
    p.versions.append(PromptVersion(version_no=1, system_prompt="", user_prompt="{{x}}", params=["x"]))
    p.versions.append(PromptVersion(version_no=2, system_prompt="", user_prompt="{{x}}", params=["x"]))
    db.add(p); db.commit(); db.refresh(p)
    v1, v2 = p.versions[0].id, p.versions[1].id
    prev = PromptEvalRun(name="prev", eval_type="single_prompt", prompt_version_ids=[v1],
                         model_ids=[2], dataset_version_ids=[3])
    prev.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=v1, model_id=2, label="L"))
    db.add(prev); db.commit(); db.refresh(prev)
    db.add(PromptEvalItem(run_id=prev.id, item_index=0, dataset_version_id=3, row_index=0,
                          inputs={}, is_good=False, evaluated_at=datetime.now(timezone.utc)))
    db.commit()
    cur = PromptEvalRun(name="cur", eval_type="single_prompt", prompt_version_ids=[v2],
                        model_ids=[2], dataset_version_ids=[3], compare_to_version_id=v1)
    cur.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=v2, model_id=2, label="L2"))
    db.add(cur); db.commit(); db.refresh(cur)
    db.add(PromptEvalItem(run_id=cur.id, item_index=0, dataset_version_id=3, row_index=0,
                          inputs={}, is_good=True, evaluated_at=datetime.now(timezone.utc)))
    db.commit()
    s2 = st.stats(db, cur.id)
    assert s2["good"] == 1 and s2["bad"] == 0
    assert s2["comparison"]["improved"] == 1 and s2["comparison"]["regressed"] == 0
    assert s2["comparison"]["comparable"] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_submit_verdict_multi_and_single tests/test_prompt_eval.py::test_stats_multi_and_single -q`
Expected: FAIL(`AttributeError: submit_verdict` / `ModuleNotFoundError: prompt_eval_stats`)

- [ ] **Step 3: 扩展 schema**

In `services/app-server/app/schemas/prompt_eval.py`, change the `ItemOut` class to add the verdict fields (keep existing fields):
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

    class Config:
        from_attributes = True
```
And add a `VerdictIn` class at the end of the file:
```python
class VerdictIn(BaseModel):
    winner_arm_id: int | None = None
    all_bad: bool = False
    is_good: bool | None = None
```

- [ ] **Step 4: 实现 verdict service**

In `services/app-server/app/services/prompt_eval_service.py`, add these imports at the top (next to the existing imports):
```python
from datetime import datetime, timezone
from app.models.prompt_eval import PromptEvalItem
```
And append this function at the end of the file:
```python
def submit_verdict(db: Session, item_id: int, body, user_id: int | None) -> PromptEvalItem | None:
    item = db.get(PromptEvalItem, item_id)
    if item is None:
        return None
    run = db.get(PromptEvalRun, item.run_id)
    if run.eval_type == "single_prompt":
        if body.is_good is None:
            raise ValueError("单 prompt 评测需提交 好 / 坏")
        item.is_good = body.is_good
        item.winner_arm_id = None
        item.all_bad = False
    else:
        if body.all_bad:
            item.all_bad = True
            item.winner_arm_id = None
        elif body.winner_arm_id is not None:
            arm = db.get(PromptEvalArm, body.winner_arm_id)
            if arm is None or arm.run_id != run.id:
                raise ValueError("winner_arm_id 不属于该评测")
            item.winner_arm_id = body.winner_arm_id
            item.all_bad = False
        else:
            raise ValueError("多臂评测需选择获胜方或『都一样坏』")
        item.is_good = None
    item.evaluated_by = user_id
    item.evaluated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(item)
    return item
```

- [ ] **Step 5: 实现 stats service**

Create `services/app-server/app/services/prompt_eval_stats.py`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.prompt import PromptVersion
from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem


def _evaluated_items(db: Session, run_id: int) -> list[PromptEvalItem]:
    return list(db.execute(select(PromptEvalItem).where(
        PromptEvalItem.run_id == run_id,
        PromptEvalItem.evaluated_at.is_not(None))).scalars())


def _all_items(db: Session, run_id: int) -> list[PromptEvalItem]:
    return list(db.execute(select(PromptEvalItem).where(PromptEvalItem.run_id == run_id)).scalars())


def _comparison(db: Session, run: PromptEvalRun) -> dict | None:
    if not run.compare_to_version_id:
        return None
    prev_ids = db.execute(
        select(PromptEvalRun.id)
        .join(PromptEvalArm, PromptEvalArm.run_id == PromptEvalRun.id)
        .where(PromptEvalRun.eval_type == "single_prompt",
               PromptEvalArm.prompt_version_id == run.compare_to_version_id,
               PromptEvalRun.id != run.id)
        .order_by(PromptEvalRun.id.desc())).scalars().all()
    cur = {(i.dataset_version_id, i.row_index): i.is_good for i in _evaluated_items(db, run.id)}
    for prev_id in prev_ids:
        prev = {(i.dataset_version_id, i.row_index): i.is_good for i in _evaluated_items(db, prev_id)}
        keys = set(cur) & set(prev)
        if not keys:
            continue
        improved = sum(1 for k in keys if prev[k] is False and cur[k] is True)
        regressed = sum(1 for k in keys if prev[k] is True and cur[k] is False)
        comparable = len(keys)
        pv = db.get(PromptVersion, run.compare_to_version_id)
        label = f"{pv.prompt.name} V{pv.version_no}" if pv else None
        return {"compare_run_id": prev_id, "compare_version_label": label,
                "comparable": comparable, "improved": improved, "regressed": regressed,
                "improved_rate": improved / comparable, "regressed_rate": regressed / comparable}
    return None


def stats(db: Session, run_id: int) -> dict | None:
    run = db.get(PromptEvalRun, run_id)
    if run is None:
        return None
    evaluated = _evaluated_items(db, run_id)
    total = len(_all_items(db, run_id))
    base = {"eval_type": run.eval_type, "evaluated": len(evaluated), "total": total}
    if run.eval_type == "single_prompt":
        good = sum(1 for i in evaluated if i.is_good is True)
        bad = sum(1 for i in evaluated if i.is_good is False)
        good_rate = good / len(evaluated) if evaluated else 0.0
        return {**base, "good": good, "bad": bad, "good_rate": good_rate,
                "comparison": _comparison(db, run)}
    # multi-arm
    wins = {a.id: 0 for a in run.arms}
    all_bad = 0
    for i in evaluated:
        if i.all_bad:
            all_bad += 1
        elif i.winner_arm_id in wins:
            wins[i.winner_arm_id] += 1
    n = len(evaluated)
    arms = [{"arm_id": a.id, "label": a.label, "prompt_version_id": a.prompt_version_id,
             "model_id": a.model_id, "wins": wins[a.id],
             "win_rate": wins[a.id] / n if n else 0.0} for a in run.arms]
    best = max(run.arms, key=lambda a: (wins[a.id], -a.arm_index)) if run.arms else None
    best_id = best.id if (best and wins.get(best.id, 0) > 0) else None
    return {**base, "arms": arms, "all_bad": all_bad, "best_arm_id": best_id}
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_submit_verdict_multi_and_single tests/test_prompt_eval.py::test_stats_multi_and_single -q`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add services/app-server/app/schemas/prompt_eval.py services/app-server/app/services/prompt_eval_service.py services/app-server/app/services/prompt_eval_stats.py services/app-server/tests/test_prompt_eval.py
git commit -m "$(printf 'feat(app-server): add verdict + stats services for prompt eval\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project C2. `submit_verdict` validates the verdict against the run's `eval_type` (multi-arm needs winner or all_bad and the arm must belong to the run; single_prompt needs is_good), then stamps evaluator+time. `stats` aggregates on the fly: multi-arm → per-arm wins/win_rate + best arm (tie-break smallest arm_index, null when nobody won); single_prompt → good/bad/rate + `_comparison` which finds the most recent evaluated single_prompt run of the previous version (`compare_to_version_id`) with overlapping `(dataset_version_id, row_index)` evaluated rows and computes improved/regressed. `run.arms` is selectin-loaded; items are queried directly (no `run.items` relationship by design). APPEND to `test_prompt_eval.py`.

---

### Task 4: API — items 扩展 + verdict + stats

**Files:**
- Modify: `services/app-server/app/api/prompt_eval.py`
- Test: `services/app-server/tests/test_prompt_eval.py` (APPEND)

- [ ] **Step 1: 追加失败测试**

Append to `services/app-server/tests/test_prompt_eval.py`:

```python
def test_verdict_and_stats_api(session_factory):
    from datetime import datetime, timezone
    from app.models.prompt_eval import PromptEvalItem
    db = session_factory()
    run, arms, it = _seed_eval_run(db, "multi_prompt", 2)
    rid, aid, iid = run.id, arms[0].id, it.id
    u = make_user(db, codes=("prompteval:read", "prompteval:annotate"), data_scope="all", email="jg@x.com")
    H = auth_headers(u.id); db.close()
    from app.main import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    # verdict
    r = c.patch(f"/prompt-evals/items/{iid}/verdict", json={"winner_arm_id": aid}, headers=H)
    assert r.status_code == 200 and r.json()["winner_arm_id"] == aid
    # 类型不符:单 prompt 字段给多臂 run
    assert c.patch(f"/prompt-evals/items/{iid}/verdict", json={"is_good": True}, headers=H).status_code == 422
    # items bucket=evaluated 含这条
    ev = c.get(f"/prompt-evals/{rid}/items?bucket=evaluated", headers=H).json()
    assert any(x["id"] == iid and x["winner_arm_id"] == aid for x in ev)
    # bucket=pending 不含
    pend = c.get(f"/prompt-evals/{rid}/items?bucket=pending", headers=H).json()
    assert all(x["id"] != iid for x in pend)
    # stats
    s = c.get(f"/prompt-evals/{rid}/stats", headers=H).json()
    assert s["evaluated"] == 1 and s["best_arm_id"] == aid


def test_verdict_requires_perm(session_factory):
    db = session_factory()
    run, arms, it = _seed_eval_run(db, "multi_prompt", 2)
    iid, aid = it.id, arms[0].id
    u = make_user(db, codes=("prompteval:read",), data_scope="all", email="ro@x.com")  # 无 annotate
    H = auth_headers(u.id); db.close()
    from app.main import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    assert c.patch(f"/prompt-evals/items/{iid}/verdict", json={"winner_arm_id": aid}, headers=H).status_code == 403
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py::test_verdict_and_stats_api tests/test_prompt_eval.py::test_verdict_requires_perm -q`
Expected: FAIL(404 / 缺路由)

- [ ] **Step 3: 改 API**

In `services/app-server/app/api/prompt_eval.py`:

(a) add imports at the top (next to existing imports):
```python
import random
from app.models.prompt_eval import PromptEvalArm
from app.schemas.prompt_eval import VerdictIn, OutputOut
from app.services import prompt_eval_stats
```
(`PromptEvalRun`, `PromptEvalItem`, `ItemOut`, `prompt_eval_service as svc`, `require`, `get_db`, `paginate` are already imported.)

(b) REPLACE the existing `list_items` function with this bucket+shuffle version:
```python
@router.get("/{run_id}/items", response_model=list[ItemOut])
def list_items(run_id: int, response: Response, bucket: str = "all",
               page: int | None = Query(None, ge=1), page_size: int = Query(20, ge=1, le=200),
               _: User = Depends(require("prompteval:read")), db: Session = Depends(get_db)):
    if not db.get(PromptEvalRun, run_id):
        raise HTTPException(404, "run not found")
    stmt = select(PromptEvalItem).where(PromptEvalItem.run_id == run_id)
    if bucket == "pending":
        stmt = stmt.where(PromptEvalItem.evaluated_at.is_(None))
    elif bucket == "evaluated":
        stmt = stmt.where(PromptEvalItem.evaluated_at.is_not(None))
    stmt = stmt.order_by(PromptEvalItem.item_index)
    items = paginate(db, stmt, response, page, page_size)
    out = []
    for it in items:
        shuffled = list(it.outputs)
        random.Random(it.id).shuffle(shuffled)   # 盲测匿名:按 item.id 稳定打乱
        out.append(ItemOut(
            id=it.id, item_index=it.item_index, dataset_version_id=it.dataset_version_id,
            row_index=it.row_index, inputs=it.inputs,
            outputs=[OutputOut.model_validate(o) for o in shuffled],
            winner_arm_id=it.winner_arm_id, all_bad=it.all_bad, is_good=it.is_good,
            annotated_by_name=it.annotated_by_name, evaluated_at=it.evaluated_at))
    return out
```

(c) add these two routes (place AFTER `list_items`):
```python
@router.patch("/items/{item_id}/verdict", response_model=ItemOut)
def submit_verdict(item_id: int, body: VerdictIn,
                   user: User = Depends(require("prompteval:annotate")), db: Session = Depends(get_db)):
    try:
        item = svc.submit_verdict(db, item_id, body, user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if item is None:
        raise HTTPException(404, "item not found")
    return ItemOut(
        id=item.id, item_index=item.item_index, dataset_version_id=item.dataset_version_id,
        row_index=item.row_index, inputs=item.inputs,
        outputs=[OutputOut.model_validate(o) for o in item.outputs],
        winner_arm_id=item.winner_arm_id, all_bad=item.all_bad, is_good=item.is_good,
        annotated_by_name=item.annotated_by_name, evaluated_at=item.evaluated_at)


@router.get("/{run_id}/stats")
def get_stats(run_id: int, _: User = Depends(require("prompteval:read")), db: Session = Depends(get_db)):
    s = prompt_eval_stats.stats(db, run_id)
    if s is None:
        raise HTTPException(404, "run not found")
    return s
```

> 注:`PATCH /items/{item_id}/verdict` 的 `items` 是静态段、与 `/{run_id}`(int 转换器)不冲突;`/{run_id}/stats` 在 `/{run_id}` 之后多一段,亦不冲突。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd services/app-server && pytest tests/test_prompt_eval.py -q`
Expected: PASS(全部 prompt_eval 测试)

- [ ] **Step 5: 全量回归**

Run: `cd services/app-server && pytest -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add services/app-server/app/api/prompt_eval.py services/app-server/tests/test_prompt_eval.py
git commit -m "$(printf 'feat(app-server): prompt-eval items bucket/shuffle + verdict + stats endpoints\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project C2. The items endpoint is extended (not replaced wholesale — same path, adds `bucket` filter + per-item shuffle of outputs by `random.Random(item.id)` for blind anonymization + verdict fields on `ItemOut`). The response is built explicitly (constructing `ItemOut` objects) rather than relying on response_model auto-serialization, because the outputs must be reordered. The verdict PATCH and stats GET reuse the services from Task 3, gated by `prompteval:annotate` / `prompteval:read`. APPEND to `test_prompt_eval.py`.

---

### Task 5: 前端 API client

**Files:**
- Modify: `frontend/src/api/client.ts`

> 验证 = `npx tsc --noEmit -p tsconfig.app.json`。

- [ ] **Step 1: 改 items 函数 + 加 verdict/stats**

In `frontend/src/api/client.ts`:

(a) extend `PromptEvalItem` type to include verdict fields — find the existing `export type PromptEvalItem = {...}` and change it to:
```typescript
export type PromptEvalItem = {
  id: number; item_index: number; dataset_version_id: number; row_index: number;
  inputs: Record<string, any>; outputs: PromptEvalOutputRow[];
  winner_arm_id: number | null; all_bad: boolean; is_good: boolean | null;
  annotated_by_name: string | null; evaluated_at: string | null;
};
```

(b) change the existing `listPromptEvalItemsPaged` to accept a bucket — replace it with:
```typescript
export const listPromptEvalItemsPaged = (id: number, p: { bucket?: string; page: number; page_size: number }) =>
  getPaginated<PromptEvalItem>(`/prompt-evals/${id}/items`, p);
```

(c) append at the END of the file:
```typescript
export const submitPromptEvalVerdict = (itemId: number, b: { winner_arm_id?: number; all_bad?: boolean; is_good?: boolean }) =>
  api.patch<PromptEvalItem>(`/prompt-evals/items/${itemId}/verdict`, b).then(r => r.data);
export type PromptEvalArmStat = { arm_id: number; label: string; prompt_version_id: number; model_id: number; wins: number; win_rate: number };
export type PromptEvalStats = {
  eval_type: string; evaluated: number; total: number;
  arms?: PromptEvalArmStat[]; all_bad?: number; best_arm_id?: number | null;
  good?: number; bad?: number; good_rate?: number;
  comparison?: { compare_run_id: number; compare_version_label: string | null; comparable: number; improved: number; regressed: number; improved_rate: number; regressed_rate: number } | null;
};
export const getPromptEvalStats = (id: number) => api.get<PromptEvalStats>(`/prompt-evals/${id}/stats`).then(r => r.data);
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
Expected: no errors

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/client.ts
git commit -m "$(printf 'feat(frontend): add prompt-eval verdict + stats + items bucket client\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project C2. `getPaginated` passes extra params (incl. `bucket`) as query params automatically (it spreads `p` into the request params), so adding `bucket` to `listPromptEvalItemsPaged`'s `p` works. The `PromptEvalItem` outputs come pre-shuffled from the backend. Stage ONLY `client.ts` (working tree has other unrelated changes).

---

### Task 6: 前端 评估工作台 + 路由

**Files:**
- Create: `frontend/src/pages/PromptEvalWorkbench.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 写工作台**

Create `frontend/src/pages/PromptEvalWorkbench.tsx`:

```tsx
import { useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../constants";
import { ArrowLeft, Check, SkipForward } from "lucide-react";
import {
  getPromptEval, listPromptEvalItemsPaged, submitPromptEvalVerdict,
  type PromptEvalDetail, type PromptEvalItem,
} from "../api/client";
import { Badge, Button, EmptyState, Pagination, TableShell } from "../ui";
import { toastError, toastSuccess } from "../toast";
import { navigate } from "../router";

const LETTERS = ["A", "B", "C", "D", "E", "F"];
const BUCKETS = [{ k: "pending", label: "未评" }, { k: "evaluated", label: "已评" }, { k: "all", label: "全部" }];

export function PromptEvalWorkbench({ runId }: { runId: number }) {
  const [run, setRun] = useState<PromptEvalDetail | null>(null);
  const [bucket, setBucket] = useState("pending");
  const [items, setItems] = useState<PromptEvalItem[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [curId, setCurId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { getPromptEval(runId).then(setRun).catch(() => toastError("加载失败")); }, [runId]);
  const reload = () => listPromptEvalItemsPaged(runId, { bucket, page, page_size: pageSize })
    .then(res => { setItems(res.items); setTotal(res.total); if (curId == null && res.items.length) setCurId(res.items[0].id); });
  useEffect(() => { setLoading(true); reload().finally(() => setLoading(false)); }, [runId, bucket, page, pageSize]);

  const cur = items.find(i => i.id === curId) ?? null;
  const single = run?.eval_type === "single_prompt";

  const goNext = () => {
    const idx = items.findIndex(i => i.id === curId);
    const next = items[idx + 1];
    if (next) setCurId(next.id);
  };

  const submit = (b: { winner_arm_id?: number; all_bad?: boolean; is_good?: boolean }) => {
    if (!cur) return;
    setBusy(true);
    submitPromptEvalVerdict(cur.id, b)
      .then(() => { toastSuccess("已评估"); reload(); goNext(); })
      .catch(e => toastError(e?.response?.data?.detail ?? "提交失败"))
      .finally(() => setBusy(false));
  };

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <Button variant="subtle" size="sm" onClick={() => navigate("/prompt-evals")}><ArrowLeft size={14} /> 返回</Button>
        <div className="text-[15px] font-semibold text-slate-800">{run?.name ?? `评测 #${runId}`} · 盲测评估</div>
      </div>

      <div className="flex gap-4 h-[calc(100vh-190px)] min-h-[480px]">
        {/* 左:item 列表 */}
        <div className="flex w-72 shrink-0 flex-col rounded-xl ring-1 ring-slate-200">
          <div className="flex gap-1 border-b border-slate-100 p-2">
            {BUCKETS.map(b => (
              <button key={b.k} onClick={() => { setBucket(b.k); setPage(1); setCurId(null); }}
                className={`rounded-md px-2 py-1 text-[12px] ${bucket === b.k ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-slate-100"}`}>
                {b.label}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-auto">
            {loading ? <div className="p-3 text-[12px] text-slate-400">加载中…</div> :
              items.length === 0 ? <div className="p-3 text-[12px] text-slate-400">无数据</div> :
                items.map(i => (
                  <button key={i.id} onClick={() => setCurId(i.id)}
                    className={`block w-full border-b border-slate-50 px-3 py-2 text-left text-[13px] ${i.id === curId ? "bg-brand-50" : "hover:bg-slate-50"}`}>
                    <span className="text-slate-700">#{i.item_index + 1}</span>
                    {i.evaluated_at && <Check size={12} className="ml-2 inline text-emerald-500" />}
                  </button>
                ))}
          </div>
          <div className="border-t border-slate-100 p-2">
            <Pagination page={page} pageSize={pageSize} total={total} onPage={setPage} onPageSize={s => { setPageSize(s); setPage(1); }} />
          </div>
        </div>

        {/* 右:评估区 */}
        <div className="flex-1 overflow-auto rounded-xl ring-1 ring-slate-200 p-5">
          {!cur ? <EmptyState title="选择左侧一条开始评估" /> : (
            <div className="flex flex-col gap-4">
              <div>
                <div className="label mb-1.5">参数输入</div>
                <div className="rounded-lg bg-slate-50 p-3 text-[13px]">
                  {Object.entries(cur.inputs).map(([k, v]) => (
                    <div key={k}><span className="text-slate-400">{k}:</span> <span className="text-slate-700">{String(v ?? "")}</span></div>
                  ))}
                </div>
              </div>

              <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${single ? 1 : cur.outputs.length}, minmax(0, 1fr))` }}>
                {cur.outputs.map((o, idx) => (
                  <div key={o.id} className="rounded-xl ring-1 ring-slate-200 p-3">
                    {!single && <Badge tone="blue">{LETTERS[idx]}</Badge>}
                    <pre className="mt-2 whitespace-pre-wrap text-[13px] text-slate-700">{o.status === "error" ? `（调用失败:${o.error}）` : o.output_text}</pre>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {single ? (
                  <>
                    <Button variant="primary" disabled={busy} onClick={() => submit({ is_good: true })}>好</Button>
                    <Button variant="danger" disabled={busy} onClick={() => submit({ is_good: false })}>坏</Button>
                  </>
                ) : (
                  <>
                    {cur.outputs.map((o, idx) => (
                      <Button key={o.id} variant="primary" disabled={busy} onClick={() => submit({ winner_arm_id: o.arm_id })}>{LETTERS[idx]} 更好</Button>
                    ))}
                    <Button variant="subtle" disabled={busy} onClick={() => submit({ all_bad: true })}>都一样坏</Button>
                  </>
                )}
                <Button variant="subtle" disabled={busy} onClick={goNext}><SkipForward size={14} /> 跳过</Button>
                {cur.evaluated_at && <span className="ml-auto text-[12px] text-slate-400">已评 · {cur.annotated_by_name ?? "?"} · {cur.evaluated_at.slice(0, 19).replace("T", " ")}</span>}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 注册路由**

In `frontend/src/App.tsx`, add an import alongside the other page imports:
```tsx
import { PromptEvalWorkbench } from "./pages/PromptEvalWorkbench";
```
And add a route branch BEFORE the `else if (path === "/prompt-evals")` line (more specific route first):
```tsx
  else if (/^\/prompt-evals\/\d+\/evaluate$/.test(path)) {
    page = <PromptEvalWorkbench runId={Number(path.split("/")[2])} />;
  }
```

- [ ] **Step 3: 类型检查 + 构建**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm run build`
Expected: no type errors; build succeeds.

If a `ui` prop differs, open `frontend/src/ui.tsx` and adjust minimally. `Button` `size="sm"`, `variant` (`primary`/`subtle`/`danger`), `Badge tone="blue"`, `Pagination`, `EmptyState` (title-only) are all used elsewhere — verify.

- [ ] **Step 4: 提交**

```bash
git add frontend/src/pages/PromptEvalWorkbench.tsx frontend/src/App.tsx
git commit -m "$(printf 'feat(frontend): add Prompt eval blind workbench (two-pane)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project C2 — the blind evaluation workbench, mirroring the badcase annotate workbench (two-pane: left filterable item list with pending/evaluated/all tabs + pagination, right the current item's anonymized A/B/C output cards + verdict buttons). Outputs arrive pre-shuffled and the cards show no arm label (blind). For single_prompt there's one output and 好/坏 buttons. The verdict submits the real `arm_id` (from the output row) which the user never sees. `navigate` is from `../router`. Stage ONLY the 2 files.

---

### Task 7: 前端 统计抽屉 + C1 列表入口

**Files:**
- Modify: `frontend/src/pages/PromptEvalsPage.tsx`

- [ ] **Step 1: 读现状**

Open `frontend/src/pages/PromptEvalsPage.tsx`. It has a runs table (`items.map(r => ...)`) with columns 名称/类型/状态/进度/创建者/创建时间. You will: add a trailing actions cell with 「评估」+「统计」buttons for `succeeded` runs, and a stats `Drawer`.

- [ ] **Step 2: 加入口 + 统计抽屉**

In `frontend/src/pages/PromptEvalsPage.tsx`:

(a) extend imports — change the `lucide-react` import to add icons and the `../api/client` import to add stats, and the `../ui` import to add `Drawer`/`Badge` if missing:
```tsx
import { ClipboardCheck, Plus, PencilLine, BarChart3 } from "lucide-react";
```
```tsx
import {
  listPromptEvalsPaged, createPromptEval, getPromptEvalOptions, getPromptEvalStats,
  type PromptEval, type PromptEvalOptions, type PromptEvalStats,
} from "../api/client";
```
Ensure `Drawer` is in the `../ui` import list (add it if not present).
Add `import { navigate } from "../router";` near the other imports.

(b) add a `statsId` state inside `PromptEvalsPage` (next to the other `useState`s):
```tsx
  const [statsId, setStatsId] = useState<number | null>(null);
```

(c) add a trailing header cell `<th className="w-44 text-right"></th>` to the table `head`, and a trailing `<td>` in the row map (inside `items.map(r => ...)`, after the 创建时间 cell):
```tsx
            <td className="text-right">
              {r.status === "succeeded" && (
                <div className="flex items-center justify-end gap-2">
                  <Button size="sm" variant="primary" onClick={() => navigate(`/prompt-evals/${r.id}/evaluate`)}><PencilLine size={13} /> 评估</Button>
                  <Button size="sm" onClick={() => setStatsId(r.id)}><BarChart3 size={13} /> 统计</Button>
                </div>
              )}
            </td>
```

(d) add the stats drawer right before the closing `</>` of the component's return (after the `{open && <NewEvalDrawer .../>}` line):
```tsx
      {statsId !== null && <StatsDrawer runId={statsId} onClose={() => setStatsId(null)} />}
```

(e) add the `StatsDrawer` component at the END of the file (after `PromptEvalsPage`):
```tsx
function StatsDrawer({ runId, onClose }: { runId: number; onClose: () => void }) {
  const [s, setS] = useState<PromptEvalStats | null>(null);
  useEffect(() => { getPromptEvalStats(runId).then(setS).catch(() => toastError("加载统计失败")); }, [runId]);
  return (
    <Drawer open onClose={onClose} title="评测统计" subtitle={s ? `已评 ${s.evaluated} / 共 ${s.total}` : undefined} width="max-w-lg">
      {!s ? <p className="text-[13px] text-slate-400">加载中…</p> : s.eval_type === "single_prompt" ? (
        <div className="flex flex-col gap-4">
          <div className="rounded-xl ring-1 ring-slate-200 p-4">
            <div className="text-[13px] text-slate-500">好率</div>
            <div className="text-[22px] font-semibold text-slate-800">{Math.round((s.good_rate ?? 0) * 100)}%</div>
            <div className="text-[12px] text-slate-400">好 {s.good} · 坏 {s.bad}</div>
          </div>
          {s.comparison ? (
            <div className="rounded-xl ring-1 ring-slate-200 p-4">
              <div className="mb-1 text-[13px] text-slate-500">对比上一版本:{s.comparison.compare_version_label}</div>
              <div className="text-[13px] text-emerald-600">变好率 {Math.round(s.comparison.improved_rate * 100)}%({s.comparison.improved} 条)</div>
              <div className="text-[13px] text-red-600">变坏率 {Math.round(s.comparison.regressed_rate * 100)}%（{s.comparison.regressed} 条)</div>
              <div className="text-[12px] text-slate-400">可对比 {s.comparison.comparable} 条</div>
            </div>
          ) : <p className="text-[13px] text-slate-400">无可对比的上一版本数据。</p>}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {(s.arms ?? []).map(a => (
            <div key={a.arm_id} className="rounded-xl ring-1 ring-slate-200 p-3">
              <div className="flex items-center gap-2">
                <span className="font-medium text-slate-800">{a.label}</span>
                {a.arm_id === s.best_arm_id && <Badge tone="green">最优</Badge>}
                <span className="ml-auto text-[13px] text-slate-600">胜率 {Math.round(a.win_rate * 100)}% · {a.wins} 胜</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full bg-brand-500" style={{ width: `${Math.round(a.win_rate * 100)}%` }} />
              </div>
            </div>
          ))}
          <div className="text-[12px] text-slate-400">都一样坏 {s.all_bad} 条</div>
        </div>
      )}
    </Drawer>
  );
}
```

- [ ] **Step 3: 类型检查 + 构建**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 4: 提交**

```bash
git add frontend/src/pages/PromptEvalsPage.tsx
git commit -m "$(printf 'feat(frontend): add eval/stats entry buttons + stats drawer on prompt-eval list\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

## Context

Sub-project C2 final task. The C1 `PromptEvalsPage` list gets per-row 「评估」(→ workbench) and 「统计」(→ stats drawer) buttons for succeeded runs. The stats drawer reveals arm labels (blind only applied during evaluation), showing multi-arm win-rate bars + best badge, or single_prompt good-rate + improve/regress vs previous version. `toastError` and `Drawer`/`Badge`/`Button` are from existing imports — verify they're imported. Stage ONLY `PromptEvalsPage.tsx`.

---

## 收尾验证(全部任务后)

- [ ] `cd services/app-server && pytest -q`(含真实 PG:21 表 / 22 权限)全绿;前端 `tsc` + `build` 通过。
- [ ] 手动冒烟:重启 app-server(迁移 023/024)→ 对一个 succeeded 的多臂评测点「评估」→ 工作台盲测(A/B/C 无标签、位置随机)选谁更好/都一样坏 → 「统计」抽屉揭晓标签显示胜率与最优;单 prompt 评测显示好率 +(若有上一版)变好/变坏率。
- [ ] 无 `prompteval:annotate` 不能提交 verdict(403)。

---

## 自审记录(对照 spec)

- **Spec 覆盖**:verdict 列+迁移 023(T1)、annotate 权限+024+计数(T2)、schema+verdict service+stats service(T3)、items 扩展(bucket+shuffle+verdict 字段)+verdict API+stats API(T4)、前端 client(T5)、工作台(T6)、统计抽屉+入口(T7)。
- **占位符**:无;每步完整代码 + 命令。
- **类型一致**:`VerdictIn`/`ItemOut` verdict 字段(T3)↔ API 构造(T4)↔ 前端 `PromptEvalItem`(T5)一致;`submit_verdict`(T3 service)↔ verdict 路由(T4)一致;`prompt_eval_stats.stats` 返回结构(T3)↔ stats 路由(T4)↔ 前端 `PromptEvalStats`(T5)↔ StatsDrawer(T7)一致(多臂 `arms/best_arm_id/all_bad`,单 prompt `good/bad/good_rate/comparison`);工作台用 `o.arm_id` 提交(T6)↔ `winner_arm_id` 校验(T3)一致。
- **计数**:T2 把 test_bootstrap→22、test_migrations_apply nperm→22(ntab 保持 21),T4 全量回归确认。
```
