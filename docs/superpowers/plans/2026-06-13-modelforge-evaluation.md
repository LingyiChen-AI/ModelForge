# ModelForge Evaluation Implementation Plan (阶段 4:评估流程执行)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现评估流程:对某个模型版本 + 评估集版本发起评估,train-worker 加载已注册模型做批量推理算指标,结果回写 `EvalRun`,前端可在同一评估集上横向对比多个模型版本(Leaderboard)。

**Architecture:** 复用现有 Celery 编排与 MLflow Registry。app-server 建 `EvalRun` 并投 `EVAL_TASK`;worker 从 MLflow 下载已注册模型产物、读评估集快照、按 task_type 批量推理算指标、把结果直接 UPDATE 回 `EvalRun`(评估行已由 app-server 创建,worker 只更新——比训练的回调更简单)。本计划落地 **classification** 评估;ner/pair/embedding 评估随各自 recipe 在阶段 5 补齐。

**Tech Stack:** 沿用 FastAPI / SQLAlchemy / Alembic / Celery / MLflow / transformers / sklearn / pytest / React。

依赖:阶段 1–3 已完成(TrainingJob/ModelVersion、classification 训练全链路、MLflow 注册)。
参考:`docs/superpowers/specs/2026-06-13-modelforge-architecture-design.md` 第 6.2 节。

---

## 文件结构(本计划锁定/新增)

```
services/app-server/app/
  models/training.py                 # 增 EvalRun 模型
  schemas/eval.py                    # 新增 EvalRunCreate / EvalRunOut
  services/eval_service.py           # 新增 create_and_dispatch
  celery_client.py                   # 增 send_eval_task
  api/eval.py                        # 新增 /eval-runs 路由 + leaderboard
  main.py                            # 注册 eval 路由
  alembic/versions/xxxx_eval_runs.py # 迁移
services/train-worker/worker/
  db.py                              # 增 set_eval_status / load_eval_run
  evaluators/__init__.py             # get_evaluator(task_type)
  evaluators/base.py                 # Evaluator 协议 + EvalResult
  evaluators/classification.py       # 分类批量推理 + 指标
  model_loader.py                    # 从 MLflow Registry 下载模型产物到本地
  tasks.py                           # 增 eval_task(EVAL_TASK)
frontend/src/
  api/client.ts                      # 增 eval API
  pages/EvalPage.tsx                 # 发起评估 + 列表 + leaderboard
  App.tsx                            # 增 /eval 路由与导航
```

---

### Task 1: EvalRun 模型 + 迁移

**Files:**
- Modify: `services/app-server/app/models/training.py`
- Modify: `services/app-server/app/models/__init__.py`
- Test: `services/app-server/tests/test_evalrun_model.py`

- [ ] **Step 1: 失败测试**
```python
# services/app-server/tests/test_evalrun_model.py
from app.models.base import Base
import app.models  # noqa

def test_eval_runs_table():
    assert "eval_runs" in Base.metadata.tables
    cols = Base.metadata.tables["eval_runs"].columns.keys()
    assert {"id", "model_version_id", "dataset_version_id", "metric_config",
            "status", "celery_task_id", "results", "per_sample_uri", "error"} <= set(cols)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_evalrun_model.py -q` → KeyError: 'eval_runs'

- [ ] **Step 3: 实现模型**（追加到 `app/models/training.py` 末尾）
```python
class EvalRun(Base, TimestampMixin):
    __tablename__ = "eval_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"))
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"))
    metric_config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(default=JobStatus.PENDING.value)
    celery_task_id: Mapped[str | None] = mapped_column(nullable=True)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    per_sample_uri: Mapped[str | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(nullable=True)
```
更新 `app/models/__init__.py`：
```python
from app.models.training import TrainingJob, ModelVersion, EvalRun
__all__ = ["Base", "User", "Dataset", "DatasetVersion", "TrainingJob", "ModelVersion", "EvalRun"]
```

- [ ] **Step 4: 运行确认通过 + 迁移**

Run:
```bash
cd services/app-server && python -m pytest tests/test_evalrun_model.py -q   # PASS
alembic revision --autogenerate -m "eval_runs" && alembic upgrade head
```
确认迁移仅新增 `eval_runs` 表，down_revision 指向 training_jobs/model_versions 迁移(31a899d550be)。用 python inspect 确认表存在。

- [ ] **Step 5: 提交**
```bash
git add services/app-server/app/models services/app-server/alembic/versions
git commit -m "feat(app-server): EvalRun model and migration"
```

---

### Task 2: app-server 评估投递 API

**Files:**
- Create: `services/app-server/app/schemas/eval.py`
- Create: `services/app-server/app/services/eval_service.py`
- Create: `services/app-server/app/api/eval.py`
- Modify: `services/app-server/app/celery_client.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_eval_api.py`

- [ ] **Step 1: 失败测试**（mock celery send_eval_task；SQLite）
```python
# services/app-server/tests/test_eval_api.py
from fastapi.testclient import TestClient

def test_create_eval_run(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.dataset import Dataset, DatasetVersion
    from app.models.training import TrainingJob, ModelVersion
    eng = create_engine(f"sqlite:///{tmp_path}/t.db"); Base.metadata.create_all(eng)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    s = dbmod.SessionLocal()
    ds = Dataset(name="e", kind="eval", task_type="classification"); s.add(ds); s.commit()
    dv = DatasetVersion(dataset_id=ds.id, version_no=1, storage_uri="s3://x/y",
                        row_count=4, checksum="c", note=""); s.add(dv); s.commit()
    job = TrainingJob(name="j", dataset_version_id=dv.id, base_model="bert-base",
                      task_type="classification", hyperparams={}); s.add(job); s.commit()
    mv = ModelVersion(name="ModelForge-j", source_training_job_id=job.id,
                      mlflow_model_name="ModelForge-j", mlflow_version="1",
                      task_type="classification", base_model="bert-base", train_metrics={})
    s.add(mv); s.commit()
    mv_id, dv_id = mv.id, dv.id; s.close()

    import app.services.eval_service as es
    sent = {}
    def fake_send(run_id):
        sent["run"] = run_id
        return "celery-eval-1"
    monkeypatch.setattr(es, "send_eval_task", fake_send)

    from app.main import app
    c = TestClient(app)
    r = c.post("/eval-runs", json={"model_version_id": mv_id, "dataset_version_id": dv_id})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending" and body["celery_task_id"] == "celery-eval-1"
    assert sent["run"] == body["id"]
```

- [ ] **Step 2: 运行确认失败**（路由不存在）

- [ ] **Step 3: 实现**
```python
# services/app-server/app/celery_client.py  (追加)
from modelforge_common.task_names import EVAL_TASK

def send_eval_task(eval_run_id: int) -> str:
    result = _celery.send_task(EVAL_TASK, args=[eval_run_id])
    return result.id
```
```python
# services/app-server/app/schemas/eval.py
from pydantic import BaseModel

class EvalRunCreate(BaseModel):
    model_version_id: int
    dataset_version_id: int
    metric_config: dict = {}

class EvalRunOut(BaseModel):
    id: int
    model_version_id: int
    dataset_version_id: int
    status: str
    celery_task_id: str | None
    results: dict
    error: str | None
    class Config: from_attributes = True
```
```python
# services/app-server/app/services/eval_service.py
from sqlalchemy.orm import Session
from app.models.training import EvalRun, ModelVersion
from app.models.dataset import DatasetVersion
from app.celery_client import send_eval_task   # module-level name (monkeypatchable)

def create_and_dispatch(db: Session, body) -> EvalRun:
    if not db.get(ModelVersion, body.model_version_id):
        raise ValueError("model_version not found")
    if not db.get(DatasetVersion, body.dataset_version_id):
        raise ValueError("dataset_version not found")
    run = EvalRun(model_version_id=body.model_version_id,
                  dataset_version_id=body.dataset_version_id,
                  metric_config=body.metric_config)
    db.add(run); db.commit(); db.refresh(run)
    run.celery_task_id = send_eval_task(run.id)
    db.commit(); db.refresh(run)
    return run
```
```python
# services/app-server/app/api/eval.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.training import EvalRun
from app.schemas.eval import EvalRunCreate, EvalRunOut
from app.services import eval_service

router = APIRouter(prefix="/eval-runs", tags=["eval"])

@router.post("", response_model=EvalRunOut, status_code=201)
def create(body: EvalRunCreate, db: Session = Depends(get_db)):
    try:
        return eval_service.create_and_dispatch(db, body)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[EvalRunOut])
def list_runs(dataset_version_id: int | None = None, db: Session = Depends(get_db)):
    q = select(EvalRun).order_by(EvalRun.id.desc())
    if dataset_version_id is not None:
        q = q.where(EvalRun.dataset_version_id == dataset_version_id)
    return db.execute(q).scalars().all()

@router.get("/{run_id}", response_model=EvalRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(EvalRun, run_id)
    if not run:
        raise HTTPException(404, "not found")
    return run
```
`app/main.py` 追加:`from app.api import eval` + `app.include_router(eval.router)`。

- [ ] **Step 4: 运行确认通过**（target + 全套 `python -m pytest -q`）

- [ ] **Step 5: 提交**
```bash
git add services/app-server/app/schemas/eval.py services/app-server/app/services/eval_service.py services/app-server/app/api/eval.py services/app-server/app/celery_client.py services/app-server/app/main.py services/app-server/tests/test_eval_api.py
git commit -m "feat(app-server): eval run dispatch API"
```

---

### Task 3: worker EvalRun 状态/加载工具

**Files:**
- Modify: `services/train-worker/worker/db.py`
- Test: `services/train-worker/tests/test_eval_db.py`

- [ ] **Step 1: 失败测试**（SQLite + 原生 SQL）
```python
# services/train-worker/tests/test_eval_db.py
from sqlalchemy import create_engine, text
from worker.db import set_eval_status, load_eval_run, JobStatus

def test_set_eval_status_and_load(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE eval_runs (id INTEGER PRIMARY KEY, model_version_id INTEGER, "
                       "dataset_version_id INTEGER, status TEXT, results TEXT, error TEXT)"))
        c.execute(text("CREATE TABLE model_versions (id INTEGER PRIMARY KEY, mlflow_model_name TEXT, "
                       "mlflow_version TEXT, task_type TEXT)"))
        c.execute(text("CREATE TABLE dataset_versions (id INTEGER PRIMARY KEY, storage_uri TEXT)"))
        c.execute(text("INSERT INTO model_versions VALUES (7,'ModelForge-j','2','classification')"))
        c.execute(text("INSERT INTO dataset_versions VALUES (3,'s3://b/k')"))
        c.execute(text("INSERT INTO eval_runs (id,model_version_id,dataset_version_id,status) "
                       "VALUES (1,7,3,'pending')"))
    set_eval_status(eng, 1, JobStatus.RUNNING)
    info = load_eval_run(eng, 1)
    assert info["mlflow_model_name"] == "ModelForge-j" and info["mlflow_version"] == "2"
    assert info["task_type"] == "classification" and info["storage_uri"] == "s3://b/k"
    set_eval_status(eng, 1, JobStatus.SUCCEEDED, results={"accuracy": 0.8})
    with eng.connect() as c:
        row = c.execute(text("SELECT status, results FROM eval_runs WHERE id=1")).one()
    assert row.status == "succeeded" and '"accuracy"' in row.results
```

- [ ] **Step 2: 运行确认失败**（ImportError: set_eval_status）

- [ ] **Step 3: 实现**（追加到 `worker/db.py`，文件已有 `import json`? 若无则加）
```python
import json  # 确保文件顶部已 import json（没有就加）

def set_eval_status(engine: Engine, eval_run_id: int, status: JobStatus,
                    results: dict | None = None, error: str | None = None) -> None:
    sets = ["status = :status"]
    params = {"status": status.value, "id": eval_run_id}
    if results is not None:
        sets.append("results = :res"); params["res"] = json.dumps(results)
    if error is not None:
        sets.append("error = :err"); params["err"] = error
    with engine.begin() as c:
        c.execute(text(f"UPDATE eval_runs SET {', '.join(sets)} WHERE id = :id"), params)

def load_eval_run(engine: Engine, eval_run_id: int) -> dict:
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT r.id, m.mlflow_model_name, m.mlflow_version, m.task_type, "
            "v.storage_uri, r.metric_config FROM eval_runs r "
            "JOIN model_versions m ON m.id = r.model_version_id "
            "JOIN dataset_versions v ON v.id = r.dataset_version_id "
            "WHERE r.id = :id"), {"id": eval_run_id}).mappings().one()
        return dict(row)
```
注意:测试的 eval_runs 表无 metric_config 列，但 load_eval_run 查询了 r.metric_config。为兼容,本测试不调用 load_eval_run 的 metric_config 路径——实际 PG 有该列。但 SQLite 测试会因缺列报错。**因此**:测试里 CREATE TABLE eval_runs 必须包含 metric_config 列。请在测试的 CREATE 语句加 `metric_config TEXT` 列(在 Step 1 测试里补上 `metric_config TEXT` 列定义),保持查询一致。

- [ ] **Step 4: 运行确认通过**

- [ ] **Step 5: 提交**
```bash
git add services/train-worker/worker/db.py services/train-worker/tests/test_eval_db.py
git commit -m "feat(train-worker): eval run status/load helpers"
```

---

### Task 4: 分类评估器(批量推理 + 指标)

**Files:**
- Create: `services/train-worker/worker/evaluators/__init__.py`
- Create: `services/train-worker/worker/evaluators/base.py`
- Create: `services/train-worker/worker/evaluators/classification.py`
- Test: `services/train-worker/tests/test_classification_evaluator.py`

- [ ] **Step 1: 失败测试**（用一个临时训练出的小模型目录做真实评估;标记 slow）
```python
# services/train-worker/tests/test_classification_evaluator.py
import pandas as pd, pytest
from worker.evaluators import get_evaluator
from worker.evaluators.classification import ClassificationEvaluator

def test_get_evaluator_classification():
    assert isinstance(get_evaluator("classification"), ClassificationEvaluator)

@pytest.mark.slow
def test_classification_evaluate_returns_metrics(tmp_path):
    # 先用 recipe 训练一个 tiny 模型到 model_dir
    from worker.recipes.classification import ClassificationRecipe
    train_df = pd.DataFrame({"text": ["good","bad","great","awful"]*4,
                             "label": ["pos","neg","pos","neg"]*4})
    ClassificationRecipe().train(df=train_df, base_model="prajjwal1/bert-tiny",
        hyperparams={"epochs": 1, "batch_size": 4, "max_length": 16},
        output_dir=str(tmp_path))
    eval_df = pd.DataFrame({"text": ["good","bad"], "label": ["pos","neg"]})
    metrics = ClassificationEvaluator().evaluate(model_dir=str(tmp_path), df=eval_df)
    assert "accuracy" in metrics and "f1" in metrics
    assert 0.0 <= metrics["accuracy"] <= 1.0
```

- [ ] **Step 2: 运行确认失败**（ModuleNotFoundError: worker.evaluators）

- [ ] **Step 3: 实现**
```python
# worker/evaluators/base.py
class Evaluator:
    def evaluate(self, model_dir: str, df) -> dict:
        raise NotImplementedError
```
```python
# worker/evaluators/classification.py
import json, os
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from worker.evaluators.base import Evaluator

class ClassificationEvaluator(Evaluator):
    def evaluate(self, model_dir: str, df) -> dict:
        with open(os.path.join(model_dir, "label_map.json")) as f:
            label2id = json.load(f)
        tok = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        model.eval()
        texts = df["text"].tolist()
        enc = tok(texts, truncation=True, padding=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = model(**enc).logits.cpu().numpy()
        pred = np.argmax(logits, axis=-1)
        y = df["label"].map(label2id).to_numpy()
        p, r, f1, _ = precision_recall_fscore_support(y, pred, average="macro", zero_division=0)
        return {"accuracy": float(accuracy_score(y, pred)),
                "precision": float(p), "recall": float(r), "f1": float(f1),
                "n_samples": int(len(df))}
```
```python
# worker/evaluators/__init__.py
from worker.evaluators.base import Evaluator
from worker.evaluators.classification import ClassificationEvaluator

def get_evaluator(task_type: str) -> Evaluator:
    if task_type == "classification":
        return ClassificationEvaluator()
    raise NotImplementedError(f"evaluator for {task_type} not implemented yet")
```

- [ ] **Step 4: 运行确认通过**（fast 测试必过；slow 测试跑真实训练+评估,~30s）

- [ ] **Step 5: 提交**
```bash
git add services/train-worker/worker/evaluators services/train-worker/tests/test_classification_evaluator.py
git commit -m "feat(train-worker): classification evaluator with batch inference"
```

---

### Task 5: worker 模型下载 + eval_task 编排

**Files:**
- Create: `services/train-worker/worker/model_loader.py`
- Modify: `services/train-worker/worker/tasks.py`
- Test: `services/train-worker/tests/test_eval_task.py`

- [ ] **Step 1: 失败测试**（stub 下载/快照/评估,验证编排 + 状态/结果写回）
```python
# services/train-worker/tests/test_eval_task.py
from sqlalchemy import create_engine, text
import pandas as pd, worker.tasks as tasks

def test_eval_task_orchestration(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE eval_runs (id INTEGER PRIMARY KEY, model_version_id INTEGER, "
                       "dataset_version_id INTEGER, status TEXT, results TEXT, error TEXT, metric_config TEXT)"))
        c.execute(text("CREATE TABLE model_versions (id INTEGER PRIMARY KEY, mlflow_model_name TEXT, "
                       "mlflow_version TEXT, task_type TEXT)"))
        c.execute(text("CREATE TABLE dataset_versions (id INTEGER PRIMARY KEY, storage_uri TEXT)"))
        c.execute(text("INSERT INTO model_versions VALUES (7,'ModelForge-j','2','classification')"))
        c.execute(text("INSERT INTO dataset_versions VALUES (3,'s3://b/k')"))
        c.execute(text("INSERT INTO eval_runs (id,model_version_id,dataset_version_id,status,metric_config) "
                       "VALUES (1,7,3,'pending','{}')"))
    monkeypatch.setattr(tasks, "build_engine", lambda: eng)
    monkeypatch.setattr(tasks, "download_model", lambda name, version: str(tmp_path))
    monkeypatch.setattr(tasks, "read_snapshot",
                        lambda uri: pd.DataFrame({"text": ["a"], "label": ["x"]}))
    monkeypatch.setattr(tasks, "run_evaluator",
                        lambda task_type, model_dir, df: {"accuracy": 0.75, "f1": 0.7})

    tasks.eval_task.run(eval_run_id=1)

    with eng.connect() as c:
        row = c.execute(text("SELECT status, results FROM eval_runs WHERE id=1")).one()
    assert row.status == "succeeded" and '"accuracy": 0.75' in row.results
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**
```python
# worker/model_loader.py
import mlflow
from worker.mlflow_utils import _configure_mlflow_s3_env
from worker.config import settings

def download_model(mlflow_model_name: str, mlflow_version: str) -> str:
    """Download a registered model's artifacts to a local dir, return its path."""
    _configure_mlflow_s3_env()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    return mlflow.artifacts.download_artifacts(
        artifact_uri=f"models:/{mlflow_model_name}/{mlflow_version}")
```
在 `worker/tasks.py` 增加(顶部 import + 模块级函数 + 任务):
```python
from modelforge_common.task_names import TRAIN_TASK, EVAL_TASK
from worker.db import build_engine, set_job_status, load_job, set_eval_status, load_eval_run
from worker.model_loader import download_model
from worker.evaluators import get_evaluator

def run_evaluator(task_type, model_dir, df):
    return get_evaluator(task_type).evaluate(model_dir=model_dir, df=df)

@celery_app.task(name=EVAL_TASK, bind=True)
def eval_task(self, eval_run_id: int):
    engine = build_engine()
    set_eval_status(engine, eval_run_id, JobStatus.RUNNING)
    try:
        run = load_eval_run(engine, eval_run_id)
        model_dir = download_model(run["mlflow_model_name"], run["mlflow_version"])
        df = read_snapshot(run["storage_uri"])
        metrics = run_evaluator(run["task_type"], model_dir, df)
        set_eval_status(engine, eval_run_id, JobStatus.SUCCEEDED, results=metrics)
        return {"eval_run_id": eval_run_id, "metrics": metrics}
    except Exception as e:
        set_eval_status(engine, eval_run_id, JobStatus.FAILED, error=str(e))
        raise
```
保持 `import worker.tasks` 在 celery_app.py 末尾（已在）。注意 `download_model`、`read_snapshot`、`run_evaluator`、`build_engine` 都是 tasks 模块级名字(可被 monkeypatch)。`EVAL_TASK` 现在也注册到 celery。

- [ ] **Step 4: 运行确认通过**（target test + `-m "not slow"` 全套；确认 test_celery_app 仍过，且 EVAL_TASK 已注册——可加一行断言或在 test_celery_app 里已有 TRAIN_TASK，不必改）

- [ ] **Step 5: 提交**
```bash
git add services/train-worker/worker/model_loader.py services/train-worker/worker/tasks.py services/train-worker/tests/test_eval_task.py
git commit -m "feat(train-worker): model download and eval task orchestration"
```

---

### Task 6: Leaderboard + 前端评估页

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/EvalPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 前端 api 追加**
```ts
// frontend/src/api/client.ts  (追加)
export type EvalRun = { id: number; model_version_id: number; dataset_version_id: number; status: string; results: Record<string, number>; error: string | null };
export const listEvalRuns = (datasetVersionId?: number) =>
  api.get<EvalRun[]>("/eval-runs", { params: datasetVersionId ? { dataset_version_id: datasetVersionId } : {} }).then(r => r.data);
export const createEvalRun = (b: { model_version_id: number; dataset_version_id: number }) =>
  api.post<EvalRun>("/eval-runs", b).then(r => r.data);
```

- [ ] **Step 2: EvalPage（发起评估 + 列表 + 按 dataset_version 过滤的 leaderboard 表）**
```tsx
// frontend/src/pages/EvalPage.tsx
import { useEffect, useState } from "react";
import { listEvalRuns, createEvalRun, type EvalRun } from "../api/client";

export function EvalPage() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [mvId, setMvId] = useState("");
  const [dvId, setDvId] = useState("");
  const reload = () => listEvalRuns(dvId ? Number(dvId) : undefined).then(setRuns);
  useEffect(() => { reload(); const t = setInterval(reload, 3000); return () => clearInterval(t); }, [dvId]);
  return (
    <div>
      <h2>评估</h2>
      <div>
        <input placeholder="model_version_id" value={mvId} onChange={e => setMvId(e.target.value)} />
        <input placeholder="eval dataset_version_id" value={dvId} onChange={e => setDvId(e.target.value)} />
        <button disabled={!mvId || !dvId} onClick={() =>
          createEvalRun({ model_version_id: Number(mvId), dataset_version_id: Number(dvId) }).then(reload)}>
          发起评估
        </button>
      </div>
      <table><thead><tr><th>#</th><th>模型版本</th><th>评估集版本</th><th>状态</th><th>指标</th></tr></thead>
        <tbody>{runs.map(r => <tr key={r.id}>
          <td>{r.id}</td><td>{r.model_version_id}</td><td>{r.dataset_version_id}</td>
          <td><b>{r.status}</b>{r.error ? ` (${r.error})` : ""}</td>
          <td>{JSON.stringify(r.results)}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: App.tsx 增路由 + 导航**

在 `frontend/src/App.tsx` 的 import 增 `import { EvalPage } from "./pages/EvalPage";`，在路由判断里增 `else if (path === "/eval") page = <EvalPage />;`，并在 `<nav>` 增 `<a href="/eval">评估</a>`。

- [ ] **Step 4: 构建**

Run: `cd frontend && npm run build` → exit 0，dist/ 产出。修复任何 TS 报错（type-only import）而不改行为。

- [ ] **Step 5: 提交**
```bash
git add frontend/src
git commit -m "feat(frontend): evaluation page with leaderboard"
```

---

## 自查(Self-Review)

**Spec 覆盖度(第 6.2 节评估流程):**
- 发起评估(模型版本 + 评估集版本)→ Task 1/2 ✅
- worker 加载模型 + 批量推理 + 算指标 → Task 4/5 ✅
- 结果写回 EvalRun → Task 3/5 ✅
- 同一评估集横向对比 → Task 2(按 dataset_version 过滤的列表)+ Task 6(前端表)✅
- per_sample 明细落 MinIO:本计划先存汇总指标到 `results`,`per_sample_uri` 字段预留(后续可补明细落盘),不在本计划范围 —— 已在 EvalRun 模型保留字段。

**占位符扫描:** 无 TBD;每步含完整代码。

**类型一致性:** worker `tasks.py` 的 monkeypatch 名字(build_engine/read_snapshot/run_evaluator/download_model)均模块级;`set_eval_status(results=...)`/`load_eval_run` 返回键(mlflow_model_name/mlflow_version/task_type/storage_uri/metric_config)在 Task 3 定义、Task 5 使用一致;EvalRun 字段在 Task 1 定义、Task 2 schema/Task 3 SQL 一致。

**已知前置依赖:** Task 4 slow 测试与真实 eval_task 端到端需联网(bert-tiny)与 MLflow/MinIO;CI 用 `-m "not slow"` 跳过。`download_model` 真实路径需要 MLflow 里存在已注册模型(由训练全链路产生)。
