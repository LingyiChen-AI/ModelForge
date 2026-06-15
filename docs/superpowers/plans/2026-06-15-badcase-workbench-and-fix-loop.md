# Badcase Workbench + Fix-Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Badcase list with a per-model summary table + full-page annotation workbench, and close the loop so badcase-trained models report which badcases they fixed (`V4 已修复` labels) plus a `badcase 修复率` metric.

**Architecture:** Add a `fixed_by` JSON column to `badcases` (numbered SQL migration per project 铁律). After training on a `badcase-` dataset, the worker re-runs the freshly trained model over the badcases that were in the training set, computes `badcase_fix_rate` (into metrics) and the list of fixed badcase ids, and reports them back through the existing internal result endpoint; app-server appends `{model_version_id, version_label, at}` to each fixed badcase's `fixed_by`. Frontend gets a summary table + a workbench route that steps through unannotated cases.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (app-server), Celery + transformers/sentence-transformers (train-worker), React 19 + Vite + TS + Tailwind (frontend).

**Spec:** `docs/superpowers/specs/2026-06-15-badcase-workbench-and-fix-loop-design.md`

---

## File Structure

**app-server**
- `app/models/badcase.py` — add `fixed_by` column + `is_fixed` helper
- `db/migrations/015_badcase_fixed_by.sql` — add column (idempotent)
- `app/schemas/badcase.py` — `BadcaseOut.fixed_by`, new `BadcaseSummaryOut`
- `app/services/badcase_service.py` — new `summary(db)`, `mark_fixed(...)`
- `app/api/badcase.py` — new `GET /badcases/summary`
- `app/api/training.py` — extend `TrainResultIn`, call `mark_fixed` in `report_result`

**train-worker**
- `worker/badcase_scoring.py` — new; `judge(...)` (pure) + `_predict(...)` + `score(...)`
- `worker/db.py` — `load_job` exposes `train_version_ids`; new `load_trained_badcases(...)`
- `worker/tasks.py` — `train_task` scores badcases + adds to report payload

**frontend**
- `src/api/client.ts` — `BadcaseSummary` type + `listBadcaseSummary`; `Badcase.fixed_by`
- `src/pages/BadcaseAnnotateForm.tsx` — new; task-aware input view + annotation form (extracted)
- `src/pages/BadcaseAnnotateDrawer.tsx` — use the extracted form
- `src/pages/BadcasePage.tsx` — summary table
- `src/pages/BadcaseAnnotateWorkbench.tsx` — new full-page workbench
- `src/App.tsx` — route `/badcase/annotate/:id`
- `src/pages/ModelsPage.tsx` — Chinese metric labels + `badcase 修复率` %

---

## Task 1: `fixed_by` column + migration + schema

**Files:**
- Modify: `services/app-server/app/models/badcase.py`
- Create: `services/app-server/db/migrations/015_badcase_fixed_by.sql`
- Modify: `services/app-server/app/schemas/badcase.py`
- Test: `services/app-server/tests/test_badcase_api.py` (add a case)

- [ ] **Step 1: Add the column to the model**

In `app/models/badcase.py`, add the import `JSON` is already imported. Add after the `dataset_version_id` column:

```python
    fixed_by: Mapped[list] = mapped_column(JSON, default=list)  # [{model_version_id, version_label, at}]
```

And add a helper property next to `model_version_label`:

```python
    @property
    def is_fixed(self) -> bool:
        return bool(self.fixed_by)
```

- [ ] **Step 2: Write the migration**

Create `db/migrations/015_badcase_fixed_by.sql`:

```sql
-- Track which model versions have repaired each badcase (V4 已修复 / V7 已修复).
ALTER TABLE badcases ADD COLUMN IF NOT EXISTS fixed_by JSON DEFAULT '[]'::json;
```

- [ ] **Step 3: Add `fixed_by` to the output schema**

In `app/schemas/badcase.py`, add to `BadcaseOut` (before `class Config`):

```python
    fixed_by: list = []
```

- [ ] **Step 4: Verify migration count test still passes (no new table/perm)**

Run: `cd services/app-server && .venv/bin/pytest tests/test_migrations_apply.py -q`
Expected: PASS (this migration only adds a column; table/permission counts are unchanged).

- [ ] **Step 5: Add a concrete test that `BadcaseOut` exposes `fixed_by: []`**

In `tests/test_badcase_api.py`, add (dependency-free — exercises the schema default directly):

```python
def test_badcase_out_includes_fixed_by():
    from datetime import datetime
    from app.schemas.badcase import BadcaseOut
    out = BadcaseOut(id=1, model_version_id=1, task_type="classification",
                     input={"text": "a"}, inference={}, category=None, source=None,
                     source_ref=None, status="reported", annotation=None,
                     dataset_version_id=None, created_at=datetime(2026, 6, 15))
    assert out.fixed_by == []
```

- [ ] **Step 6: Run the badcase test file**

Run: `cd services/app-server && .venv/bin/pytest tests/test_badcase_api.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/app-server/app/models/badcase.py services/app-server/db/migrations/015_badcase_fixed_by.sql services/app-server/app/schemas/badcase.py services/app-server/tests/test_badcase_api.py
git commit -m "feat(badcase): add fixed_by column + migration 015"
```

---

## Task 2: `GET /badcases/summary`

**Files:**
- Modify: `services/app-server/app/services/badcase_service.py`
- Modify: `services/app-server/app/schemas/badcase.py`
- Modify: `services/app-server/app/api/badcase.py`
- Test: `services/app-server/tests/test_badcase_api.py`

- [ ] **Step 1: Add `BadcaseSummaryOut` schema**

In `app/schemas/badcase.py`, append:

```python
class BadcaseSummaryOut(BaseModel):
    model_version_id: int
    model_name: str | None = None
    model_version_label: str | None = None
    task_type: str
    reported: int    # total badcases for this model version
    annotated: int   # status in (annotated, used)
    used: int        # status == used (already turned into a dataset)
    pending: int     # status == reported (awaiting annotation)
    fixed: int       # fixed_by non-empty
    fixed_versions: list[str] = []   # distinct model-version labels that fixed any badcase (V4, V7)
```

- [ ] **Step 2: Write a failing test for the summary aggregation**

In `tests/test_badcase_api.py`, add (follow the file's existing setup style — SQLite engine, ModelVersion rows, Badcase rows; reuse whatever helpers the file already uses):

```python
def test_badcase_summary_counts(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.training import TrainingJob, ModelVersion
    from app.models.badcase import Badcase
    eng = create_engine(f"sqlite:///{tmp_path}/s.db"); Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False); db = S()
    job = TrainingJob(name="j", dataset_version_id=1, base_model="b",
                      task_type="classification", hyperparams={}); db.add(job); db.commit()
    mv = ModelVersion(name="意图", source_training_job_id=job.id, mlflow_model_name="意图",
                      mlflow_version="3", task_type="classification", base_model="b", train_metrics={})
    db.add(mv); db.commit()
    db.add_all([
        Badcase(model_version_id=mv.id, task_type="classification", input={"text":"a"}, status="reported"),
        Badcase(model_version_id=mv.id, task_type="classification", input={"text":"b"}, status="annotated", annotation={"label":"x"}),
        Badcase(model_version_id=mv.id, task_type="classification", input={"text":"c"}, status="used",
                annotation={"label":"y"}, fixed_by=[{"model_version_id": 99, "version_label": "4"}]),
    ]); db.commit()
    from app.services.badcase_service import summary
    rows = summary(db)
    assert len(rows) == 1
    r = rows[0]
    assert r["model_version_id"] == mv.id and r["model_name"] == "意图" and r["model_version_label"] == "3"
    assert r["reported"] == 3 and r["annotated"] == 2 and r["used"] == 1
    assert r["pending"] == 1 and r["fixed"] == 1
    assert r["fixed_versions"] == ["4"]
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd services/app-server && .venv/bin/pytest tests/test_badcase_api.py::test_badcase_summary_counts -v`
Expected: FAIL with `ImportError`/`AttributeError` (no `summary`).

- [ ] **Step 4: Implement `summary` in the service**

In `app/services/badcase_service.py`, add (Python-side grouping is intentional — counting non-empty JSON across SQLite/PG dialects is not portable, and badcase volume is small):

```python
def summary(db: Session) -> list[dict]:
    cases = list(db.execute(select(Badcase)).scalars())
    by: dict[int, dict] = {}
    for c in cases:
        s = by.setdefault(c.model_version_id, {
            "model_version_id": c.model_version_id,
            "model_name": c.model_name,
            "model_version_label": c.model_version_label,
            "task_type": c.task_type,
            "reported": 0, "annotated": 0, "used": 0, "pending": 0, "fixed": 0,
            "_versions": set()})
        s["reported"] += 1
        if c.status in ("annotated", "used"):
            s["annotated"] += 1
        if c.status == "used":
            s["used"] += 1
        if c.status == "reported":
            s["pending"] += 1
        if c.fixed_by:
            s["fixed"] += 1
            for e in c.fixed_by:
                if e.get("version_label"):
                    s["_versions"].add(str(e["version_label"]))
    out = []
    for s in by.values():
        s["fixed_versions"] = sorted(s.pop("_versions"))
        out.append(s)
    return sorted(out, key=lambda x: x["model_version_id"], reverse=True)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd services/app-server && .venv/bin/pytest tests/test_badcase_api.py::test_badcase_summary_counts -v`
Expected: PASS.

- [ ] **Step 6: Add the endpoint**

In `app/api/badcase.py`, import the schema and add a route ABOVE the existing `GET /badcases/{case_id}` (so `/badcases/summary` isn't captured by the `{case_id}` path):

```python
from app.schemas.badcase import BadcaseReportIn, BadcaseAnnotateIn, BuildDatasetIn, BadcaseOut, BadcaseSummaryOut
```

```python
@router.get("/badcases/summary", response_model=list[BadcaseSummaryOut])
def badcase_summary(_: User = Depends(require("badcase:read")), db: Session = Depends(get_db)):
    return badcase_service.summary(db)
```

Place this function definition before `get_badcase` in the file.

- [ ] **Step 7: Run the full badcase test file**

Run: `cd services/app-server && .venv/bin/pytest tests/test_badcase_api.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add services/app-server/app/services/badcase_service.py services/app-server/app/schemas/badcase.py services/app-server/app/api/badcase.py services/app-server/tests/test_badcase_api.py
git commit -m "feat(badcase): GET /badcases/summary model-level aggregation"
```

---

## Task 3: `mark_fixed` + report_result writeback

**Files:**
- Modify: `services/app-server/app/services/badcase_service.py`
- Modify: `services/app-server/app/api/training.py`
- Modify: `services/app-server/app/services/mlflow_sync.py`
- Test: `services/app-server/tests/test_badcase_api.py`

- [ ] **Step 1: Write a failing test for `mark_fixed`**

In `tests/test_badcase_api.py`:

```python
def test_mark_fixed_appends_and_dedupes(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.badcase import Badcase
    eng = create_engine(f"sqlite:///{tmp_path}/f.db"); Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False); db = S()
    b = Badcase(model_version_id=1, task_type="classification", input={"text":"a"},
                status="used", annotation={"label":"x"}); db.add(b); db.commit()
    from app.services.badcase_service import mark_fixed
    mark_fixed(db, [b.id], model_version_id=5, version_label="4")
    db.refresh(b)
    assert len(b.fixed_by) == 1 and b.fixed_by[0]["model_version_id"] == 5 and b.fixed_by[0]["version_label"] == "4"
    # same model version again -> no duplicate
    mark_fixed(db, [b.id], model_version_id=5, version_label="4")
    db.refresh(b)
    assert len(b.fixed_by) == 1
    # a different version -> appended
    mark_fixed(db, [b.id], model_version_id=8, version_label="7")
    db.refresh(b)
    assert len(b.fixed_by) == 2 and b.fixed_by[1]["version_label"] == "7"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd services/app-server && .venv/bin/pytest tests/test_badcase_api.py::test_mark_fixed_appends_and_dedupes -v`
Expected: FAIL (`mark_fixed` missing).

- [ ] **Step 3: Implement `mark_fixed`**

In `app/services/badcase_service.py`, add (note: JSON columns need reassignment so SQLAlchemy detects the change):

```python
def mark_fixed(db: Session, badcase_ids: list[int], model_version_id: int, version_label: str) -> None:
    if not badcase_ids:
        return
    at = datetime.now(timezone.utc).isoformat()
    cases = list(db.execute(select(Badcase).where(Badcase.id.in_(badcase_ids))).scalars())
    for c in cases:
        existing = list(c.fixed_by or [])
        if any(e.get("model_version_id") == model_version_id for e in existing):
            continue
        existing.append({"model_version_id": model_version_id,
                         "version_label": version_label, "at": at})
        c.fixed_by = existing   # reassign so the JSON column is marked dirty
    db.commit()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd services/app-server && .venv/bin/pytest tests/test_badcase_api.py::test_mark_fixed_appends_and_dedupes -v`
Expected: PASS.

- [ ] **Step 5: Extend `TrainResultIn` to carry fixed badcase ids**

In `app/api/training.py`, change the `TrainResultIn` class:

```python
class TrainResultIn(BaseModel):
    run_id: str
    model_name: str
    version: str
    metrics: dict = {}
    badcase_fixes: list[int] = []   # ids of badcases this newly trained version now predicts correctly
```

- [ ] **Step 6: Call `mark_fixed` in `report_result`**

In `app/api/training.py`, update the endpoint body to use the newly created model version for the label/id:

```python
@router.post("/internal/{job_id}/result", status_code=201,
             dependencies=[Depends(require_internal_token)])
def report_result(job_id: int, body: TrainResultIn, db: Session = Depends(get_db)):
    mv = upsert_model_version_from_result(db, job_id, body.model_dump())
    if body.badcase_fixes:
        from app.services.badcase_service import mark_fixed
        mark_fixed(db, body.badcase_fixes, model_version_id=mv.id, version_label=mv.mlflow_version)
    return {"model_version_id": mv.id}
```

(`upsert_model_version_from_result` already ignores unknown keys in `result`, so `badcase_fixes` in the dict is harmless there. Verify by reading `app/services/mlflow_sync.py` — it only reads `model_name`, `version`, `metrics`.)

- [ ] **Step 7: Add an endpoint-level test for the writeback**

In `tests/test_badcase_api.py`, add a test that POSTs to the internal result endpoint with `badcase_fixes` and asserts the badcase got a `fixed_by` entry with the new model version's `mlflow_version`. Follow the existing internal-token test pattern if one exists in `tests/test_training_*.py`; otherwise call `report_result`/`mark_fixed` directly as in Step 1. Minimal direct-call version:

```python
def test_report_result_marks_badcases_fixed(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.training import TrainingJob
    from app.models.badcase import Badcase
    from app.services.mlflow_sync import upsert_model_version_from_result
    from app.services.badcase_service import mark_fixed
    eng = create_engine(f"sqlite:///{tmp_path}/r.db"); Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False); db = S()
    job = TrainingJob(name="j", dataset_version_id=1, base_model="b",
                      task_type="classification", hyperparams={}); db.add(job); db.commit()
    b = Badcase(model_version_id=1, task_type="classification", input={"text":"a"},
                status="used", annotation={"label":"x"}); db.add(b); db.commit()
    mv = upsert_model_version_from_result(db, job.id, {
        "model_name": "意图", "version": "4", "metrics": {"accuracy": 0.9, "badcase_fix_rate": 0.5}})
    mark_fixed(db, [b.id], model_version_id=mv.id, version_label=mv.mlflow_version)
    db.refresh(b)
    assert b.fixed_by[0]["version_label"] == "4"
    assert mv.train_metrics["badcase_fix_rate"] == 0.5
```

- [ ] **Step 8: Run the badcase + a quick full app-server suite**

Run: `cd services/app-server && .venv/bin/pytest tests/test_badcase_api.py -q && .venv/bin/pytest -q`
Expected: PASS (all).

- [ ] **Step 9: Commit**

```bash
git add services/app-server/app/services/badcase_service.py services/app-server/app/api/training.py services/app-server/tests/test_badcase_api.py
git commit -m "feat(badcase): mark fixed badcases on train result; badcase_fix_rate flows to train_metrics"
```

---

## Task 4: worker `badcase_scoring` module

**Files:**
- Create: `services/train-worker/worker/badcase_scoring.py`
- Test: `services/train-worker/tests/test_badcase_scoring.py`

The pure judgment logic (`judge`) is unit-tested; the model-loading `_predict` mirrors the existing evaluators and is validated live (loading real models in unit tests is too heavy).

- [ ] **Step 1: Write failing tests for `judge`**

Create `services/train-worker/tests/test_badcase_scoring.py`:

```python
from worker.badcase_scoring import judge


def test_judge_classification():
    assert judge("classification", "售后服务", {"label": "售后服务"}) is True
    assert judge("classification", "物流查询", {"label": "售后服务"}) is False


def test_judge_pair():
    assert judge("pair", "1", {"label": "1"}) is True
    assert judge("pair", "0", {"label": "1"}) is False


def test_judge_ner():
    assert judge("ner", ["B-PER", "I-PER", "O"], {"tags": ["B-PER", "I-PER", "O"]}) is True
    assert judge("ner", ["B-PER", "O", "O"], {"tags": ["B-PER", "I-PER", "O"]}) is False
    # length mismatch is not a fix
    assert judge("ner", ["B-PER", "I-PER"], {"tags": ["B-PER", "I-PER", "O"]}) is False


def test_judge_embedding():
    assert judge("embedding", "在设置页重置密码", {"pos": ["在设置页重置密码"]}) is True
    assert judge("embedding", "联系客服热线", {"pos": ["在设置页重置密码"]}) is False
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd services/train-worker && .venv/bin/pytest tests/test_badcase_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: worker.badcase_scoring`.

- [ ] **Step 3: Implement the module**

Create `services/train-worker/worker/badcase_scoring.py`:

```python
"""Re-run a freshly trained model over the badcases it was trained on, to judge which
ones it now predicts correctly. `judge` is the pure comparison (unit-tested); `_predict`
loads the model exactly like the evaluators do; `score` ties them together."""
import json
import os
import numpy as np


def judge(task_type: str, prediction, annotation: dict) -> bool:
    """True if `prediction` matches the human annotation (the correct answer)."""
    annotation = annotation or {}
    if task_type in ("classification", "pair"):
        return str(prediction) == str(annotation.get("label"))
    if task_type == "ner":
        return list(prediction) == list(annotation.get("tags") or [])
    if task_type == "embedding":
        return prediction in (annotation.get("pos") or [])
    return False


def _predict_classification(model_dir, inputs):
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    with open(os.path.join(model_dir, "label_map.json")) as f:
        label2id = json.load(f)
    id2label = {i: l for l, i in label2id.items()}
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir); model.eval()
    import torch
    texts = [str(x.get("text", "")) for x in inputs]
    preds = []
    for i in range(0, len(texts), 32):
        enc = tok(texts[i:i+32], truncation=True, padding=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = model(**enc).logits.cpu().numpy()
        preds.extend(id2label[int(j)] for j in np.argmax(logits, axis=-1))
    return preds


def _predict_pair(model_dir, inputs):
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir); model.eval()
    a = [str(x.get("text_a", "")) for x in inputs]
    b = [str(x.get("text_b", "")) for x in inputs]
    preds = []
    for i in range(0, len(a), 32):
        enc = tok(a[i:i+32], b[i:i+32], truncation=True, padding=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logit = model(**enc).logits.reshape(-1).cpu().numpy()
        sim = 1.0 / (1.0 + np.exp(-logit))   # same sigmoid as serving/eval
        preds.extend("1" if s >= 0.5 else "0" for s in sim)
    return preds


def _predict_ner(model_dir, inputs):
    from transformers import AutoTokenizer, AutoModelForTokenClassification
    import torch
    with open(os.path.join(model_dir, "tag_map.json")) as f:
        tag2id = json.load(f)
    id2tag = {i: t for t, i in tag2id.items()}
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForTokenClassification.from_pretrained(model_dir); model.eval()
    preds = []
    for x in inputs:
        tokens = [str(t) for t in (x.get("tokens") or [])]
        enc = tok([tokens], is_split_into_words=True, truncation=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = model(**enc).logits[0].cpu().numpy()
        p = np.argmax(logits, axis=-1)
        word_ids = enc.word_ids(batch_index=0)
        prev, seq = None, []
        for idx, wid in enumerate(word_ids):
            if wid is not None and wid != prev:
                seq.append(id2tag[int(p[idx])])
            prev = wid
        preds.append(seq)
    return preds


def _predict_embedding(model_dir, inputs):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_dir)
    preds = []
    for x in inputs:
        cands = list(x.get("candidates") or [])
        if not cands:
            preds.append(None); continue
        qe = model.encode([str(x.get("query", ""))], normalize_embeddings=True)
        ce = model.encode(cands, normalize_embeddings=True)
        sims = (qe @ ce.T)[0]
        preds.append(cands[int(np.argmax(sims))])
    return preds


_PREDICTORS = {
    "classification": _predict_classification,
    "pair": _predict_pair,
    "ner": _predict_ner,
    "embedding": _predict_embedding,
}


def score(task_type: str, model_dir: str, rows: list[dict]) -> list[bool]:
    """rows = [{"input": {...}, "annotation": {...}}]; returns per-row fixed booleans."""
    if not rows:
        return []
    predictor = _PREDICTORS.get(task_type)
    if predictor is None:
        return [False] * len(rows)
    preds = predictor(model_dir, [r["input"] for r in rows])
    return [judge(task_type, p, r["annotation"]) for p, r in zip(preds, rows)]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd services/train-worker && .venv/bin/pytest tests/test_badcase_scoring.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add services/train-worker/worker/badcase_scoring.py services/train-worker/tests/test_badcase_scoring.py
git commit -m "feat(worker): badcase_scoring — per-row fix judgment for 4 task types"
```

---

## Task 5: worker integration — query trained badcases + report fixes

**Files:**
- Modify: `services/train-worker/worker/db.py`
- Modify: `services/train-worker/worker/tasks.py`
- Test: `services/train-worker/tests/test_load_trained_badcases.py`

- [ ] **Step 1: Expose `train_version_ids` from `load_job`**

In `worker/db.py`, inside `load_job`, after `train_ids = _as_id_list(...)` and before `return row`, add:

```python
        row["train_version_ids"] = train_ids
```

- [ ] **Step 2: Write a failing test for `load_trained_badcases`**

Create `services/train-worker/tests/test_load_trained_badcases.py` (uses a SQLite engine with a minimal `badcases` table so we don't depend on PG):

```python
from sqlalchemy import create_engine, text


def _mk(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/b.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE badcases (id INTEGER PRIMARY KEY, dataset_version_id INT, "
                       "input TEXT, annotation TEXT)"))
        c.execute(text("INSERT INTO badcases (id, dataset_version_id, input, annotation) VALUES "
                       "(1, 10, '{\"text\":\"a\"}', '{\"label\":\"x\"}'),"
                       "(2, 10, '{\"text\":\"b\"}', NULL),"
                       "(3, 99, '{\"text\":\"c\"}', '{\"label\":\"y\"}')"))
    return eng


def test_load_trained_badcases_filters(tmp_path):
    from worker.db import load_trained_badcases
    eng = _mk(tmp_path)
    rows = load_trained_badcases(eng, [10])
    # only id=1: dataset_version_id in [10] AND annotation not null
    assert [r["id"] for r in rows] == [1]
    assert rows[0]["input"] == {"text": "a"} and rows[0]["annotation"] == {"label": "x"}


def test_load_trained_badcases_empty(tmp_path):
    from worker.db import load_trained_badcases
    eng = _mk(tmp_path)
    assert load_trained_badcases(eng, []) == []
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd services/train-worker && .venv/bin/pytest tests/test_load_trained_badcases.py -v`
Expected: FAIL (`load_trained_badcases` missing).

- [ ] **Step 4: Implement `load_trained_badcases`**

In `worker/db.py`, add (handles both JSON-as-text on SQLite and dict on PG):

```python
def load_trained_badcases(engine: Engine, version_ids: list[int]) -> list[dict]:
    """Annotated badcases whose dataset_version is in `version_ids` (i.e. were in this
    training set). Returns [{id, input, annotation}] with JSON parsed."""
    if not version_ids:
        return []
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, input, annotation FROM badcases "
            "WHERE dataset_version_id IN :ids AND annotation IS NOT NULL"
        ).bindparams(bindparam("ids", expanding=True)), {"ids": version_ids}).mappings().all()
    out = []
    for r in rows:
        out.append({"id": r["id"],
                    "input": _as_json(r["input"]),
                    "annotation": _as_json(r["annotation"])})
    return out


def _as_json(v):
    if isinstance(v, (dict, list)) or v is None:
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return v
```

Ensure `from sqlalchemy import bindparam` is imported at the top of `worker/db.py` (it already imports from sqlalchemy; add `bindparam` to that import). `json` is already imported (used by `set_eval_status`).

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd services/train-worker && .venv/bin/pytest tests/test_load_trained_badcases.py -v`
Expected: PASS.

- [ ] **Step 6: Wire scoring into `train_task`**

In `worker/tasks.py`, add the import near the top with the other worker imports:

```python
from worker import badcase_scoring
from worker.db import load_trained_badcases
```

Inside `train_task`, within the `with tempfile.TemporaryDirectory() as out:` block, AFTER `version = _register_run_model(run_id, model_name)` and still inside the `with` (so `result.artifact_dir` still exists), compute fixes:

```python
            badcase_fixes = []
            try:
                bc_rows = load_trained_badcases(engine, job.get("train_version_ids") or [])
                if bc_rows:
                    fixed = badcase_scoring.score(
                        job["task_type"], result.artifact_dir,
                        [{"input": r["input"], "annotation": r["annotation"]} for r in bc_rows])
                    if fixed:
                        result.metrics["badcase_fix_rate"] = float(sum(fixed)) / len(fixed)
                        badcase_fixes = [r["id"] for r, ok in zip(bc_rows, fixed) if ok]
            except Exception:
                badcase_fixes = []  # scoring is best-effort; never fail a successful training
```

Then change the existing `report_result(...)` call to pass the fixes:

```python
        try:
            report_result(training_job_id, run_id, model_name, str(version), result.metrics,
                          badcase_fixes=badcase_fixes)
        except Exception:
            pass
```

(`badcase_fixes` is defined inside the `with` block; move its initialization to just before the `with` block — `badcase_fixes = []` — so it is in scope at the `report_result` call. Place `badcase_fixes = []` right after `model_name = job.get(...)`.)

- [ ] **Step 7: Extend `report_result` to send fixes**

In `worker/tasks.py`, update `report_result`:

```python
def report_result(training_job_id: int, run_id: str, model_name: str,
                  version: str, metrics: dict, badcase_fixes: list | None = None) -> None:
    requests.post(
        f"{settings.app_server_url}/training-jobs/internal/{training_job_id}/result",
        json={"run_id": run_id, "model_name": model_name, "version": version,
              "metrics": {k: float(v) for k, v in metrics.items()
                          if isinstance(v, (int, float))},
              "badcase_fixes": badcase_fixes or []},
        headers={"X-Internal-Token": settings.internal_token}, timeout=10)
```

- [ ] **Step 8: Run the worker test suite**

Run: `cd services/train-worker && .venv/bin/pytest -q`
Expected: PASS (existing tests + new ones; `train_task` itself isn't unit-tested — it's integration).

- [ ] **Step 9: Commit**

```bash
git add services/train-worker/worker/db.py services/train-worker/worker/tasks.py services/train-worker/tests/test_load_trained_badcases.py
git commit -m "feat(worker): score trained badcases post-training and report fixes"
```

---

## Task 6: frontend client — summary type + fixed_by

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add `fixed_by` to the `Badcase` type**

In `src/api/client.ts`, in the `Badcase` type, add after `dataset_version_id`:

```typescript
  fixed_by: { model_version_id: number; version_label: string; at?: string }[];
```

- [ ] **Step 2: Add the summary type + fetcher**

After `export const listBadcaseRules = ...`, add:

```typescript
export type BadcaseSummary = {
  model_version_id: number;
  model_name: string | null;
  model_version_label: string | null;
  task_type: string;
  reported: number;
  annotated: number;
  used: number;
  pending: number;
  fixed: number;
  fixed_versions: string[];
};
export const listBadcaseSummary = () =>
  api.get<BadcaseSummary[]>("/badcases/summary").then(r => r.data);
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS (no new errors).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(badcase-ui): client types for summary + fixed_by"
```

---

## Task 7: extract `BadcaseAnnotateForm` component

**Files:**
- Create: `frontend/src/pages/BadcaseAnnotateForm.tsx`
- Modify: `frontend/src/pages/BadcaseAnnotateDrawer.tsx`

- [ ] **Step 1: Create the reusable form component**

Create `frontend/src/pages/BadcaseAnnotateForm.tsx`. It owns the input/inference display + the task-aware annotation fields, and reports validity + value up via props (controlled):

```tsx
import { type Badcase } from "../api/client";
import { Field, Input } from "../ui";

export function annotationValid(t: string, val: Record<string, any>): boolean {
  return Boolean(
    (t === "classification" && val.label) ||
    (t === "pair" && (val.label === "0" || val.label === "1")) ||
    (t === "ner" && Array.isArray(val.tags) && val.tags.length > 0) ||
    (t === "embedding" && Array.isArray(val.pos) && val.pos.length > 0),
  );
}

export function BadcaseAnnotateForm({
  badcase,
  val,
  onChange,
}: {
  badcase: Badcase;
  val: Record<string, any>;
  onChange: (v: Record<string, any>) => void;
}) {
  const t = badcase.task_type;
  const set = (k: string, v: any) => onChange({ ...val, [k]: v });
  const candidates: string[] = badcase.input?.candidates ?? [];

  return (
    <div className="flex flex-col gap-4">
      <Field label="模型输入">
        <pre className="rounded-lg bg-slate-50 p-2 font-mono text-[12px] text-slate-600 whitespace-pre-wrap break-all">
          {JSON.stringify(badcase.input, null, 2)}
        </pre>
      </Field>
      <Field label="模型推理(错误)">
        <pre className="rounded-lg bg-slate-50 p-2 font-mono text-[12px] text-slate-500 whitespace-pre-wrap break-all">
          {JSON.stringify(badcase.inference, null, 2)}
        </pre>
      </Field>

      {t === "classification" && (
        <Field label="正确标签 label">
          <Input value={val.label ?? ""} onChange={e => set("label", e.target.value)} placeholder="如 售后服务" />
        </Field>
      )}

      {t === "pair" && (
        <Field label="正确标签(1=相似 / 0=不相似)">
          <Input value={val.label ?? ""} onChange={e => set("label", e.target.value.trim())} placeholder="0 或 1" />
        </Field>
      )}

      {t === "ner" && (
        <Field label="正确 tags(逗号分隔,与 tokens 等长)">
          <Input
            value={(val.tags ?? []).join(",")}
            onChange={e => set("tags", e.target.value.split(",").map((x: string) => x.trim()).filter(Boolean))}
            placeholder="B-PER,I-PER,O,B-LOC,I-LOC"
          />
        </Field>
      )}

      {t === "embedding" && (
        <Field label="逐个标注候选(pos=相关 / neg=不相关)">
          <div className="flex flex-col gap-1.5">
            {candidates.map(cand => {
              const inPos = ((val.pos ?? []) as string[]).includes(cand);
              const inNeg = ((val.neg ?? []) as string[]).includes(cand);
              const mark = (key: "pos" | "neg") => {
                const other = key === "pos" ? "neg" : "pos";
                onChange({
                  ...val,
                  [key]: [...new Set([...((val[key] ?? []) as string[]), cand])],
                  [other]: ((val[other] ?? []) as string[]).filter(x => x !== cand),
                });
              };
              return (
                <div key={cand} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2">
                  <span className="flex-1 truncate text-[13px] text-slate-700">{cand}</span>
                  <button
                    className={"rounded-md px-2.5 py-1 text-[12px] cursor-pointer " +
                      (inPos ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-600")}
                    onClick={() => mark("pos")}
                  >相关</button>
                  <button
                    className={"rounded-md px-2.5 py-1 text-[12px] cursor-pointer " +
                      (inNeg ? "bg-rose-600 text-white" : "bg-slate-100 text-slate-600")}
                    onClick={() => mark("neg")}
                  >不相关</button>
                </div>
              );
            })}
          </div>
        </Field>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Rewrite `BadcaseAnnotateDrawer` to use the form**

Replace the body of `frontend/src/pages/BadcaseAnnotateDrawer.tsx` so it renders `BadcaseAnnotateForm` and uses `annotationValid`:

```tsx
import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { annotateBadcase, type Badcase } from "../api/client";
import { Button, Drawer } from "../ui";
import { toastError, toastSuccess } from "../toast";
import { BadcaseAnnotateForm, annotationValid } from "./BadcaseAnnotateForm";

export function BadcaseAnnotateDrawer({
  badcase, onClose, onSaved,
}: { badcase: Badcase | null; onClose: () => void; onSaved: () => void }) {
  const [val, setVal] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => { setVal(badcase?.annotation ?? {}); }, [badcase]);

  const valid = badcase ? annotationValid(badcase.task_type, val) : false;

  const save = () => {
    if (!badcase) return;
    setBusy(true);
    annotateBadcase(badcase.id, val)
      .then(() => { toastSuccess("已标注"); onSaved(); })
      .catch(() => toastError("标注失败"))
      .finally(() => setBusy(false));
  };

  return (
    <Drawer
      open={badcase !== null}
      onClose={onClose}
      title={badcase ? `标注 Badcase #${badcase.id}` : "标注"}
      subtitle="补充正确答案;标注后可被选入 badcase- 训练集。"
      footer={
        <div className="flex items-center justify-end gap-2">
          <Button variant="subtle" disabled={busy} onClick={onClose}>取消</Button>
          <Button variant="primary" disabled={!valid} loading={busy} onClick={save}>
            <Check size={16} /> 保存标注
          </Button>
        </div>
      }
    >
      {badcase && <BadcaseAnnotateForm badcase={badcase} val={val} onChange={setVal} />}
    </Drawer>
  );
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/BadcaseAnnotateForm.tsx frontend/src/pages/BadcaseAnnotateDrawer.tsx
git commit -m "refactor(badcase-ui): extract reusable BadcaseAnnotateForm"
```

---

## Task 8: workbench route + page

**Files:**
- Create: `frontend/src/pages/BadcaseAnnotateWorkbench.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create the workbench page**

Create `frontend/src/pages/BadcaseAnnotateWorkbench.tsx`. It loads the model version's pending queue, steps through one at a time, and offers a "build dataset" action for already-annotated cases:

```tsx
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, Database } from "lucide-react";
import {
  listBadcases, listBadcaseSummary, annotateBadcase, buildBadcaseDataset,
  type Badcase, type BadcaseSummary,
} from "../api/client";
import { Button, PageHeader, EmptyState } from "../ui";
import { toastError, toastSuccess } from "../toast";
import { navigate } from "../router";
import { BadcaseAnnotateForm, annotationValid } from "./BadcaseAnnotateForm";

const TASK_LABEL: Record<string, string> = {
  classification: "分类", ner: "序列标注", pair: "句对", embedding: "向量检索",
};

export function BadcaseAnnotateWorkbench({ modelVersionId }: { modelVersionId: number }) {
  const [queue, setQueue] = useState<Badcase[]>([]);
  const [sum, setSum] = useState<BadcaseSummary | null>(null);
  const [val, setVal] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const reloadSummary = () =>
    listBadcaseSummary().then(s => setSum(s.find(x => x.model_version_id === modelVersionId) ?? null));

  useEffect(() => {
    setLoading(true);
    Promise.all([
      listBadcases({ model_version_id: modelVersionId, status: "reported" }),
      reloadSummary(),
    ]).then(([q]) => setQueue(q)).finally(() => setLoading(false));
  }, [modelVersionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const current = queue[0] ?? null;
  useEffect(() => { setVal(current?.annotation ?? {}); }, [current]);

  const valid = current ? annotationValid(current.task_type, val) : false;

  const save = () => {
    if (!current) return;
    setBusy(true);
    annotateBadcase(current.id, val)
      .then(() => {
        toastSuccess("已标注");
        setQueue(q => q.slice(1));   // pop to next
        reloadSummary();
      })
      .catch(() => toastError("标注失败"))
      .finally(() => setBusy(false));
  };

  const build = () => {
    setBusy(true);
    listBadcases({ model_version_id: modelVersionId, status: "annotated" })
      .then(cases => {
        if (cases.length === 0) { toastError("没有已标注未生成的 badcase"); return Promise.reject(); }
        return buildBadcaseDataset(cases.map(c => c.id));
      })
      .then(res => { if (res) { toastSuccess(`已生成训练集 ${res.dataset_name}`); reloadSummary(); } })
      .catch(() => {})
      .finally(() => setBusy(false));
  };

  const title = useMemo(
    () => sum ? `${sum.model_name ?? sum.model_version_id} · V${sum.model_version_label ?? "?"}` : "标注工作台",
    [sum],
  );

  return (
    <div>
      <PageHeader
        title={title}
        subtitle={sum ? `${TASK_LABEL[sum.task_type] ?? sum.task_type} · 已标注 ${sum.annotated} / 待标注 ${sum.pending}` : "标注工作台"}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="subtle" onClick={() => navigate("/badcase")}><ArrowLeft size={16} /> 返回</Button>
            <Button variant="primary" disabled={busy || !(sum && sum.annotated > sum.used)} onClick={build}>
              <Database size={16} /> 生成 badcase- 训练集
            </Button>
          </div>
        }
      />
      {loading ? null : current ? (
        <div className="max-w-3xl rounded-xl border border-slate-200 bg-white p-5">
          <div className="mb-3 text-[13px] text-slate-500">
            Badcase #{current.id} · 剩余待标注 {queue.length}
          </div>
          <BadcaseAnnotateForm badcase={current} val={val} onChange={setVal} />
          <div className="mt-5 flex items-center justify-end gap-2">
            <Button variant="subtle" disabled={busy} onClick={() => setQueue(q => [...q.slice(1), q[0]])}>
              跳过
            </Button>
            <Button variant="primary" disabled={!valid} loading={busy} onClick={save}>
              <Check size={16} /> 保存并下一条
            </Button>
          </div>
        </div>
      ) : (
        <EmptyState icon={<Check size={20} />} title="全部标注完成" hint="该模型暂无待标注 badcase。" />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add the route in `App.tsx`**

In `src/App.tsx`, add the import:

```tsx
import { BadcaseAnnotateWorkbench } from "./pages/BadcaseAnnotateWorkbench";
```

Replace the badcase route line with a workbench-aware match. Find:

```tsx
  else if (path.startsWith("/badcase")) page = <BadcasePage />;
```

Replace with:

```tsx
  else if (path.match(/^\/badcase\/annotate\/(\d+)$/)) {
    page = <BadcaseAnnotateWorkbench modelVersionId={Number(path.match(/^\/badcase\/annotate\/(\d+)$/)![1])} />;
  }
  else if (path.startsWith("/badcase")) page = <BadcasePage />;
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/BadcaseAnnotateWorkbench.tsx frontend/src/App.tsx
git commit -m "feat(badcase-ui): full-page annotation workbench + route"
```

---

## Task 9: BadcasePage summary table

**Files:**
- Modify: `frontend/src/pages/BadcasePage.tsx`

- [ ] **Step 1: Rewrite BadcasePage as a model summary table**

Replace `frontend/src/pages/BadcasePage.tsx` with a summary table. Keep the "查看上报规则" drawer (it already exists). The page now lists one row per model version with counts and a 标注 action:

```tsx
import { useEffect, useState } from "react";
import { Bug, BookText, PencilLine } from "lucide-react";
import { listBadcaseSummary, listBadcaseRules, type BadcaseSummary } from "../api/client";
import { Badge, Button, Drawer, EmptyState, PageHeader, TableShell } from "../ui";
import { toastError } from "../toast";
import { navigate } from "../router";

const TASK_LABEL: Record<string, string> = {
  classification: "分类", ner: "序列标注", pair: "句对", embedding: "向量检索",
};

export function BadcasePage() {
  const [rows, setRows] = useState<BadcaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [rules, setRules] = useState<any[]>([]);

  const openRules = () => {
    setRulesOpen(true);
    if (rules.length === 0) listBadcaseRules().then(setRules).catch(() => toastError("加载规则失败"));
  };

  useEffect(() => {
    setLoading(true);
    listBadcaseSummary().then(setRows).catch(() => toastError("加载失败")).finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader
        title="Badcase"
        subtitle="按模型版本汇总上报的坏例;点「标注」进入工作台逐条标注,标注后可生成 badcase- 训练集修复。"
        actions={<Button variant="subtle" onClick={openRules}><BookText size={16} /> 查看上报规则</Button>}
      />

      {loading ? null : rows.length === 0 ? (
        <EmptyState icon={<Bug size={20} />} title="暂无 badcase" hint="通过 API 上报后,这里按模型版本归类。" />
      ) : (
        <TableShell head={
          <tr>
            <th className="px-4 py-2.5 text-left font-medium">模型</th>
            <th className="px-4 py-2.5 text-left font-medium">类型</th>
            <th className="px-4 py-2.5 text-left font-medium">上报</th>
            <th className="px-4 py-2.5 text-left font-medium">已标注</th>
            <th className="px-4 py-2.5 text-left font-medium">已生成训练集</th>
            <th className="px-4 py-2.5 text-left font-medium">已修复</th>
            <th className="px-4 py-2.5 text-right font-medium">操作</th>
          </tr>
        }>
          {rows.map(r => (
            <tr key={r.model_version_id} className="border-t border-slate-100">
              <td className="px-4 py-3">
                <span className="font-medium text-slate-800">{r.model_name ?? r.model_version_id}</span>
                <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11.5px] text-slate-600">V{r.model_version_label ?? "?"}</span>
              </td>
              <td className="px-4 py-3"><Badge tone="gray">{TASK_LABEL[r.task_type] ?? r.task_type}</Badge></td>
              <td className="px-4 py-3 text-slate-700">{r.reported}</td>
              <td className="px-4 py-3 text-slate-700">{r.annotated}{r.pending > 0 && <span className="ml-1 text-[12px] text-amber-600">(待 {r.pending})</span>}</td>
              <td className="px-4 py-3 text-slate-700">{r.used}</td>
              <td className="px-4 py-3">
                {r.fixed > 0 ? (
                  <div className="flex flex-wrap items-center gap-1">
                    {r.fixed_versions.map(v => <Badge key={v} tone="green">V{v} 已修复</Badge>)}
                    <span className="text-[12px] text-slate-500">共 {r.fixed}</span>
                  </div>
                ) : <span className="text-slate-400">—</span>}
              </td>
              <td className="px-4 py-3 text-right">
                <Button size="sm" variant="primary" onClick={() => navigate(`/badcase/annotate/${r.model_version_id}`)}>
                  <PencilLine size={14} /> 标注
                </Button>
              </td>
            </tr>
          ))}
        </TableShell>
      )}

      <Drawer open={rulesOpen} onClose={() => setRulesOpen(false)} title="上报规则" subtitle="各任务类型的上报字段契约与示例。">
        <div className="flex flex-col gap-4">
          {rules.map((r: any) => (
            <div key={r.task_type} className="rounded-lg border border-slate-200 p-3">
              <div className="mb-1.5 font-medium text-slate-800">{TASK_LABEL[r.task_type] ?? r.task_type}</div>
              <div className="text-[12px] text-slate-500">input 字段:<span className="font-mono">{(r.input_keys ?? []).join(", ")}</span></div>
              <div className="text-[12px] text-slate-500">标注字段:<span className="font-mono">{(r.annotation_keys ?? []).join(", ")}</span></div>
              <pre className="mt-2 rounded bg-slate-50 p-2 font-mono text-[11.5px] text-slate-600 whitespace-pre-wrap break-all">{JSON.stringify(r.example, null, 2)}</pre>
            </div>
          ))}
        </div>
      </Drawer>
    </div>
  );
}
```

- [ ] **Step 2: Confirm `Badge` supports the `green`/`gray` tones and `Button` supports `size="sm"`**

Run: `cd frontend && grep -n "tone\|size" src/ui.tsx | head`
Expected: confirms `Badge` has a `tone` prop accepting `green`/`gray`, and `Button` accepts `size`. If `green` isn't a valid tone, use the closest existing positive tone (check `STATUS_TONE`/`Badge` definition) and adjust.

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/BadcasePage.tsx
git commit -m "feat(badcase-ui): model-summary table replaces grouped list"
```

---

## Task 10: model-detail metrics — Chinese labels + fix rate %

**Files:**
- Modify: `frontend/src/pages/ModelsPage.tsx`

- [ ] **Step 1: Add a metric label/format helper to the `Metrics` component**

In `src/pages/ModelsPage.tsx`, locate the `Metrics` component (around line 14-26). Update its rendering to map known keys to Chinese labels and render rates as percentages:

```tsx
const METRIC_LABEL: Record<string, string> = {
  badcase_fix_rate: "badcase 修复率",
  accuracy: "准确率", precision: "精确率", recall: "召回率", f1: "F1",
};
function fmtMetric(k: string, v: number | string): string {
  if (typeof v !== "number") return String(v);
  if (k === "badcase_fix_rate" || k.startsWith("recall@")) return (v * 100).toFixed(1) + "%";
  return Number.isInteger(v) ? String(v) : v.toFixed(3);
}
```

Then in the `Metrics` map, change the rendered cell to:

```tsx
          {METRIC_LABEL[k] ?? k}=<span className="text-slate-900">{fmtMetric(k, v)}</span>
```

(Keep the surrounding JSX/markup as-is; only swap the label + value formatting.)

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ModelsPage.tsx
git commit -m "feat(models-ui): show badcase 修复率 (%) + Chinese metric labels"
```

---

## Final verification

- [ ] **Run all backend + worker tests**

```bash
cd services/app-server && .venv/bin/pytest -q
cd ../train-worker && .venv/bin/pytest -q
cd ../common && .venv/bin/pytest -q 2>/dev/null || true
```
Expected: all PASS.

- [ ] **Frontend build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```
Expected: build succeeds.

- [ ] **Apply migration to PG (app start auto-applies; or manual)**

```bash
cd services/app-server && .venv/bin/python -m app.migrate
```
Expected: `015_badcase_fixed_by` applied; `badcases.fixed_by` column exists.

- [ ] **Manual smoke (optional, with services running):** report a badcase via curl (see `docs/badcase-report-curl.md`), open Badcase page → summary row shows count → 标注 enters workbench → annotate → 生成 badcase- 训练集 → train a model on it → model detail shows `badcase 修复率`, summary shows `N 已修复`.

- [ ] **Final commit (if any uncommitted)**

```bash
git status
```
