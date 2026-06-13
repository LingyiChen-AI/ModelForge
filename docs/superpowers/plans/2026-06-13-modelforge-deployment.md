# ModelForge Deployment Implementation Plan (阶段 6:model-server 在线部署)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** 把已注册的模型版本一键部署为在线推理服务:model-server 从 MLflow Registry 拉权重加载,按 task_type 暴露 `/predict`(分类/NER)、`/embed`(向量)、`/similarity`(句对);app-server 提供 `Deployment` 管理(创建/列表/停止),创建时通知 model-server 加载。

**Architecture:** model-server 持有一个内存模型库(model_version_id → 已加载 predictor),`POST /load` 时从 MLflow 下载产物并按 task_type 构建 predictor;推理端点按 model_version_id 路由到已加载模型。app-server 的 `Deployment` 表记录部署元数据,创建/停止时通过 HTTP 调 model-server 的 /load / /unload(best-effort,失败回写状态)。

**Tech Stack:** FastAPI、transformers(<5)、torch、sentence-transformers、mlflow;app-server 用 requests 调 model-server。

依赖:阶段 1–5 完成(四类 recipe/evaluator、MLflow 注册、worker model_loader)。参考 spec 第 6.3 节。

---

## 文件结构(新增/修改)

```
services/model-server/
  pyproject.toml                 # 加 sentence-transformers、boto3、pandas? (predict 用不到 pandas)
  server/
    config.py                    # 新增 settings(mlflow + s3 creds)
    model_loader.py              # 新增 从 MLflow 下载产物(复用 worker 思路)
    predictors/
      __init__.py                # build_predictor(task_type, model_dir)
      base.py                    # Predictor 协议
      classification.py          # predict(texts) -> [{label, score}]
      ner.py                     # predict(token_lists) -> [[tag]]
      pair.py                    # similarity(pairs) -> [score]
      embedding.py               # embed(texts) -> [[float]]
    store.py                     # ModelStore: load/get/unload(内存)
    main.py                      # /health /load /predict /embed /similarity /loaded DELETE
  tests/
services/app-server/app/
  models/training.py             # 增 Deployment 模型
  schemas/deployment.py
  services/deployment_service.py # create/stop + 通知 model-server
  modelserver_client.py          # HTTP 调 model-server
  api/deployment.py
  main.py                        # 注册路由
  alembic/versions/xxxx_deployments.py
frontend/src/
  api/client.ts                  # 增 deployment API
  pages/DeployPage.tsx
  App.tsx                        # 增 /deploy 路由/导航
```

---

### Task 1: Deployment 模型 + 迁移(app-server)

**Files:** modify `services/app-server/app/models/training.py`, modify `app/models/__init__.py`, test `tests/test_deployment_model.py`.

- [ ] **Step 1: 失败测试**
```python
# services/app-server/tests/test_deployment_model.py
from app.models.base import Base
import app.models  # noqa

def test_deployments_table():
    assert "deployments" in Base.metadata.tables
    cols = Base.metadata.tables["deployments"].columns.keys()
    assert {"id","model_version_id","endpoint","mode","status","replicas","config","error"} <= set(cols)
```

- [ ] **Step 2: 确认失败** `python -m pytest tests/test_deployment_model.py -q`

- [ ] **Step 3: 实现**(追加到 `app/models/training.py`,复用已 import 的 ForeignKey/JSON/Mapped/mapped_column/Base/TimestampMixin)
```python
class Deployment(Base, TimestampMixin):
    __tablename__ = "deployments"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"))
    endpoint: Mapped[str | None] = mapped_column(nullable=True)
    mode: Mapped[str] = mapped_column(default="online")
    status: Mapped[str] = mapped_column(default="pending")
    replicas: Mapped[int] = mapped_column(default=1)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(nullable=True)
```
`app/models/__init__.py`:增 `Deployment` 到 import 与 `__all__`。

- [ ] **Step 4: 确认通过 + 迁移**
```bash
cd services/app-server && python -m pytest tests/test_deployment_model.py -q
alembic revision --autogenerate -m "deployments" && alembic upgrade head
```
迁移应仅新增 deployments(include_object 过滤已就位),down_revision 指向 eval_runs 迁移。python inspect 确认。

- [ ] **Step 5: 提交**
```bash
git add services/app-server/app/models services/app-server/alembic/versions
git commit -m "feat(app-server): Deployment model and migration"
```

---

### Task 2: model-server 配置 + 模型下载 + predictors

**Files:** modify `services/model-server/pyproject.toml`; create `server/config.py`, `server/model_loader.py`, `server/predictors/{__init__,base,classification,ner,pair,embedding}.py`; test `tests/test_predictors.py`.

- [ ] **Step 1: 依赖** — pyproject dependencies 加 `"sentence-transformers>=3.0"`, `"boto3>=1.34"`, `"scikit-learn>=1.5"`(分类 predictor 不需要 sklearn,但 ner 不需要;embedding 需 sentence-transformers)。装:`pip install sentence-transformers boto3`(多半已装)。保持 transformers<5(pyproject 里把 `"transformers>=4.44"` 改为 `"transformers>=4.44,<5"`)。

- [ ] **Step 2: 失败测试**(fast 工厂测试 + slow 用 recipe 训练 tiny 模型后做 predict)
```python
# services/model-server/tests/test_predictors.py
import pandas as pd, pytest
from server.predictors import build_predictor
from server.predictors.classification import ClassificationPredictor

def test_build_predictor_unknown():
    with pytest.raises(NotImplementedError):
        build_predictor("nope", "/tmp")

@pytest.mark.slow
def test_classification_predictor(tmp_path):
    # 复用 train-worker 的 recipe 产出一个分类模型(同一 conda env 可 import)
    import sys; sys.path.insert(0, "/Users/chenhao/codes/myself/ModelForge/services/train-worker")
    from worker.recipes.classification import ClassificationRecipe
    df = pd.DataFrame({"text": ["good","bad","great","awful"]*4, "label": ["pos","neg","pos","neg"]*4})
    ClassificationRecipe().train(df=df, base_model="prajjwal1/bert-tiny",
        hyperparams={"epochs":1,"batch_size":4,"max_length":16}, output_dir=str(tmp_path))
    pred = build_predictor("classification", str(tmp_path))
    out = pred.predict(["good", "awful"])
    assert len(out) == 2 and "label" in out[0] and "score" in out[0]
```

- [ ] **Step 3: 确认失败** `cd services/model-server && python -m pytest tests/test_predictors.py -q`

- [ ] **Step 4: 实现 config + loader**
```python
# server/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mlflow_tracking_uri: str = "http://localhost:5000"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
settings = Settings()
```
```python
# server/model_loader.py
import os
import mlflow
from server.config import settings
def _configure_s3_env():
    os.environ["AWS_ACCESS_KEY_ID"] = settings.s3_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = settings.s3_secret_key
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = settings.s3_endpoint_url
def download_model(mlflow_model_name: str, mlflow_version: str) -> str:
    _configure_s3_env()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    return mlflow.artifacts.download_artifacts(
        artifact_uri=f"models:/{mlflow_model_name}/{mlflow_version}")
```

- [ ] **Step 5: 实现 predictors**
```python
# server/predictors/base.py
class Predictor:
    pass
```
```python
# server/predictors/classification.py
import json, os
import numpy as np, torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from server.predictors.base import Predictor
class ClassificationPredictor(Predictor):
    def __init__(self, model_dir):
        with open(os.path.join(model_dir, "label_map.json")) as f:
            self.id2label = {v: k for k, v in json.load(f).items()}
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir); self.model.eval()
    def predict(self, texts):
        enc = self.tok(texts, truncation=True, padding=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = self.model(**enc).logits
        probs = torch.softmax(logits, dim=-1).cpu().numpy()
        out = []
        for row in probs:
            i = int(np.argmax(row))
            out.append({"label": self.id2label[i], "score": float(row[i])})
        return out
```
```python
# server/predictors/ner.py
import json, os
import numpy as np, torch
from transformers import AutoTokenizer, AutoModelForTokenClassification
from server.predictors.base import Predictor
class NERPredictor(Predictor):
    def __init__(self, model_dir):
        with open(os.path.join(model_dir, "tag_map.json")) as f:
            self.id2tag = {v: k for k, v in json.load(f).items()}
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForTokenClassification.from_pretrained(model_dir); self.model.eval()
    def predict(self, token_lists):
        results = []
        for tokens in token_lists:
            enc = self.tok([tokens], is_split_into_words=True, truncation=True,
                           max_length=256, return_tensors="pt")
            with torch.no_grad():
                logits = self.model(**enc).logits[0].cpu().numpy()
            p = np.argmax(logits, axis=-1)
            word_ids = enc.word_ids(batch_index=0)
            prev, tags = None, []
            for idx, wid in enumerate(word_ids):
                if wid is not None and wid != prev:
                    tags.append(self.id2tag[int(p[idx])])
                prev = wid
            results.append(tags)
        return results
```
```python
# server/predictors/pair.py
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from server.predictors.base import Predictor
class PairPredictor(Predictor):
    def __init__(self, model_dir):
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir); self.model.eval()
    def similarity(self, pairs):
        a = [p[0] for p in pairs]; b = [p[1] for p in pairs]
        enc = self.tok(a, b, truncation=True, padding=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = self.model(**enc).logits.reshape(-1).cpu().numpy()
        return [float(x) for x in logits]
```
```python
# server/predictors/embedding.py
from sentence_transformers import SentenceTransformer
from server.predictors.base import Predictor
class EmbeddingPredictor(Predictor):
    def __init__(self, model_dir):
        self.model = SentenceTransformer(model_dir)
    def embed(self, texts):
        return [[float(x) for x in v] for v in self.model.encode(texts, normalize_embeddings=True)]
```
```python
# server/predictors/__init__.py
from server.predictors.classification import ClassificationPredictor
from server.predictors.ner import NERPredictor
from server.predictors.pair import PairPredictor
from server.predictors.embedding import EmbeddingPredictor
def build_predictor(task_type: str, model_dir: str):
    m = {"classification": ClassificationPredictor, "ner": NERPredictor,
         "pair": PairPredictor, "embedding": EmbeddingPredictor}
    if task_type not in m:
        raise NotImplementedError(f"predictor for {task_type} not implemented")
    return m[task_type](model_dir)
```

- [ ] **Step 6: 确认通过**(fast 必过;slow 训练+predict)。

- [ ] **Step 7: 提交**
```bash
git add services/model-server/pyproject.toml services/model-server/server/config.py services/model-server/server/model_loader.py services/model-server/server/predictors services/model-server/tests/test_predictors.py
git commit -m "feat(model-server): config, model loader and per-task predictors"
```

---

### Task 3: model-server ModelStore + 推理端点

**Files:** create `server/store.py`; modify `server/main.py`; test `tests/test_server_api.py`.

- [ ] **Step 1: 失败测试**(stub build_predictor/download_model;用 TestClient 验证 load→predict→unload)
```python
# services/model-server/tests/test_server_api.py
from fastapi.testclient import TestClient

def test_load_predict_unload(monkeypatch):
    import server.main as m

    class FakePred:
        def predict(self, texts): return [{"label": "pos", "score": 0.9} for _ in texts]
    monkeypatch.setattr(m, "download_model", lambda name, version: "/tmp/x")
    monkeypatch.setattr(m, "build_predictor", lambda task_type, model_dir: FakePred())

    c = TestClient(m.app)
    r = c.post("/load", json={"model_version_id": 5, "mlflow_model_name": "ModelForge-j",
                              "mlflow_version": "1", "task_type": "classification"})
    assert r.status_code == 200 and r.json()["loaded"] is True

    r = c.post("/predict", json={"model_version_id": 5, "texts": ["hi", "yo"]})
    assert r.status_code == 200 and len(r.json()["predictions"]) == 2

    assert 5 in c.get("/loaded").json()["model_version_ids"]
    assert c.request("DELETE", "/loaded/5").status_code == 200
    assert 5 not in c.get("/loaded").json()["model_version_ids"]

def test_predict_not_loaded():
    import server.main as m
    c = TestClient(m.app)
    r = c.post("/predict", json={"model_version_id": 999, "texts": ["x"]})
    assert r.status_code == 404
```

- [ ] **Step 2: 确认失败**

- [ ] **Step 3: 实现 store**
```python
# server/store.py
from server.model_loader import download_model
from server.predictors import build_predictor

class ModelStore:
    def __init__(self):
        self._models = {}   # model_version_id -> (task_type, predictor)
    def load(self, model_version_id, mlflow_model_name, mlflow_version, task_type):
        model_dir = download_model(mlflow_model_name, mlflow_version)
        self._models[model_version_id] = (task_type, build_predictor(task_type, model_dir))
    def get(self, model_version_id):
        return self._models.get(model_version_id)
    def unload(self, model_version_id):
        return self._models.pop(model_version_id, None) is not None
    def loaded_ids(self):
        return list(self._models.keys())

store = ModelStore()
```

- [ ] **Step 4: 实现 main(端点)** — `server/main.py`(替换/扩展,保留 /health):
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from server.store import store
# import names referenced by ModelStore so tests can monkeypatch them on `server.main`
from server.model_loader import download_model  # noqa: re-exported for monkeypatch
from server.predictors import build_predictor    # noqa: re-exported for monkeypatch

app = FastAPI(title="ModelForge model-server")

@app.get("/health")
def health():
    return {"status": "ok"}

class LoadReq(BaseModel):
    model_version_id: int
    mlflow_model_name: str
    mlflow_version: str
    task_type: str

@app.post("/load")
def load(req: LoadReq):
    store.load(req.model_version_id, req.mlflow_model_name, req.mlflow_version, req.task_type)
    return {"loaded": True, "model_version_id": req.model_version_id}

class PredictReq(BaseModel):
    model_version_id: int
    texts: list[str]

@app.post("/predict")
def predict(req: PredictReq):
    entry = store.get(req.model_version_id)
    if not entry:
        raise HTTPException(404, "model not loaded")
    task_type, pred = entry
    if task_type not in ("classification",) and not hasattr(pred, "predict"):
        raise HTTPException(400, f"/predict not supported for {task_type}")
    if task_type == "ner":
        return {"predictions": pred.predict([t.split() for t in req.texts])}
    return {"predictions": pred.predict(req.texts)}

class EmbedReq(BaseModel):
    model_version_id: int
    texts: list[str]

@app.post("/embed")
def embed(req: EmbedReq):
    entry = store.get(req.model_version_id)
    if not entry:
        raise HTTPException(404, "model not loaded")
    task_type, pred = entry
    if task_type != "embedding":
        raise HTTPException(400, "/embed requires an embedding model")
    return {"embeddings": pred.embed(req.texts)}

class SimReq(BaseModel):
    model_version_id: int
    pairs: list[tuple[str, str]]

@app.post("/similarity")
def similarity(req: SimReq):
    entry = store.get(req.model_version_id)
    if not entry:
        raise HTTPException(404, "model not loaded")
    task_type, pred = entry
    if task_type != "pair":
        raise HTTPException(400, "/similarity requires a pair model")
    return {"scores": pred.similarity(req.pairs)}

@app.get("/loaded")
def loaded():
    return {"model_version_ids": store.loaded_ids()}

@app.delete("/loaded/{model_version_id}")
def unload(model_version_id: int):
    ok = store.unload(model_version_id)
    if not ok:
        raise HTTPException(404, "not loaded")
    return {"unloaded": True}
```
注意:`download_model` 与 `build_predictor` 在 main.py 顶层 import,使 `monkeypatch.setattr(server.main, "download_model", ...)` 生效——但 `store.load` 调用的是 `server.store` 里 import 的名字。为让测试的 monkeypatch 生效,改 `ModelStore.load` 通过 `server.main` 的名字?更简单:让测试 monkeypatch `server.store.download_model` 和 `server.store.build_predictor`。**因此** 调整测试的 monkeypatch 目标为 `server.store`(import server.store as s; monkeypatch.setattr(s, "download_model", ...))。请相应修改测试里两行 monkeypatch 的目标模块为 `server.store`(其余断言不变),并删除 main.py 里那两行 re-export 注释 import(避免误导)。保持端点逻辑不变。

- [ ] **Step 5: 确认通过**(`python -m pytest tests/test_server_api.py -q` + 全套 `python -m pytest -q`)

- [ ] **Step 6: 提交**
```bash
git add services/model-server/server/store.py services/model-server/server/main.py services/model-server/tests/test_server_api.py
git commit -m "feat(model-server): in-memory model store and inference endpoints"
```

---

### Task 4: app-server Deployment API(通知 model-server)

**Files:** create `app/schemas/deployment.py`, `app/modelserver_client.py`, `app/services/deployment_service.py`, `app/api/deployment.py`; modify `app/config.py`(加 model_server_url)、`app/main.py`; test `tests/test_deployment_api.py`.

- [ ] **Step 1: 失败测试**(SQLite;monkeypatch model-server 通知)
```python
# services/app-server/tests/test_deployment_api.py
from fastapi.testclient import TestClient

def test_create_and_stop_deployment(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.training import TrainingJob, ModelVersion
    eng = create_engine(f"sqlite:///{tmp_path}/t.db"); Base.metadata.create_all(eng)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    s = dbmod.SessionLocal()
    job = TrainingJob(name="j", dataset_version_id=1, base_model="b",
                      task_type="classification", hyperparams={}); s.add(job); s.commit()
    mv = ModelVersion(name="ModelForge-j", source_training_job_id=job.id,
                      mlflow_model_name="ModelForge-j", mlflow_version="1",
                      task_type="classification", base_model="b", train_metrics={})
    s.add(mv); s.commit(); mv_id = mv.id; s.close()

    import app.services.deployment_service as ds
    calls = {}
    monkeypatch.setattr(ds, "notify_load", lambda mv: calls.setdefault("load", mv.id))
    monkeypatch.setattr(ds, "notify_unload", lambda mvid: calls.setdefault("unload", mvid))

    from app.main import app
    c = TestClient(app)
    r = c.post("/deployments", json={"model_version_id": mv_id})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "running" and calls["load"] == mv_id

    r = c.post(f"/deployments/{body['id']}/stop")
    assert r.status_code == 200 and r.json()["status"] == "stopped"
    assert calls["unload"] == mv_id
```

- [ ] **Step 2: 确认失败**

- [ ] **Step 3: 实现**
```python
# app/config.py — Settings 增字段
    model_server_url: str = "http://localhost:8001"
```
```python
# app/modelserver_client.py
import requests
from app.config import settings

def load_on_server(model_version) -> None:
    requests.post(f"{settings.model_server_url}/load", json={
        "model_version_id": model_version.id,
        "mlflow_model_name": model_version.mlflow_model_name,
        "mlflow_version": model_version.mlflow_version,
        "task_type": model_version.task_type}, timeout=30).raise_for_status()

def unload_on_server(model_version_id: int) -> None:
    requests.delete(f"{settings.model_server_url}/loaded/{model_version_id}", timeout=10)
```
```python
# app/schemas/deployment.py
from pydantic import BaseModel
class DeploymentCreate(BaseModel):
    model_version_id: int
    config: dict = {}
class DeploymentOut(BaseModel):
    id: int
    model_version_id: int
    status: str
    endpoint: str | None
    error: str | None
    class Config: from_attributes = True
```
```python
# app/services/deployment_service.py
from sqlalchemy.orm import Session
from app.models.training import Deployment, ModelVersion
from app.config import settings
from app.modelserver_client import load_on_server as notify_load, unload_on_server as notify_unload

def create(db: Session, body) -> Deployment:
    mv = db.get(ModelVersion, body.model_version_id)
    if not mv:
        raise ValueError("model_version not found")
    dep = Deployment(model_version_id=mv.id, config=body.config,
                     endpoint=f"{settings.model_server_url}/predict")
    db.add(dep); db.commit(); db.refresh(dep)
    try:
        notify_load(mv)
        dep.status = "running"
    except Exception as e:
        dep.status = "failed"; dep.error = str(e)
    db.commit(); db.refresh(dep)
    return dep

def stop(db: Session, deployment_id: int) -> Deployment:
    dep = db.get(Deployment, deployment_id)
    if not dep:
        raise ValueError("deployment not found")
    try:
        notify_unload(dep.model_version_id)
    except Exception:
        pass
    dep.status = "stopped"
    db.commit(); db.refresh(dep)
    return dep
```
```python
# app/api/deployment.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.training import Deployment
from app.schemas.deployment import DeploymentCreate, DeploymentOut
from app.services import deployment_service

router = APIRouter(prefix="/deployments", tags=["deployment"])

@router.post("", response_model=DeploymentOut, status_code=201)
def create(body: DeploymentCreate, db: Session = Depends(get_db)):
    try:
        return deployment_service.create(db, body)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[DeploymentOut])
def list_deployments(db: Session = Depends(get_db)):
    return db.execute(select(Deployment).order_by(Deployment.id.desc())).scalars().all()

@router.post("/{deployment_id}/stop", response_model=DeploymentOut)
def stop(deployment_id: int, db: Session = Depends(get_db)):
    try:
        return deployment_service.stop(db, deployment_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
```
`app/main.py`:`from app.api import deployment` + `app.include_router(deployment.router)`。
注意:测试 monkeypatch `deployment_service.notify_load`/`notify_unload`,故 service 用 `from app.modelserver_client import load_on_server as notify_load, unload_on_server as notify_unload` 引入模块级名字(已如上)。

- [ ] **Step 4: 确认通过**(target + 全套 `python -m pytest -q`)

- [ ] **Step 5: 提交**
```bash
git add services/app-server/app/schemas/deployment.py services/app-server/app/modelserver_client.py services/app-server/app/services/deployment_service.py services/app-server/app/api/deployment.py services/app-server/app/config.py services/app-server/app/main.py services/app-server/tests/test_deployment_api.py
git commit -m "feat(app-server): deployment management API"
```

---

### Task 5: 前端部署页

**Files:** modify `frontend/src/api/client.ts`; create `frontend/src/pages/DeployPage.tsx`; modify `frontend/src/App.tsx`.

- [ ] **Step 1: api 追加**
```ts
export type Deployment = { id: number; model_version_id: number; status: string; endpoint: string | null; error: string | null };
export const listDeployments = () => api.get<Deployment[]>("/deployments").then(r => r.data);
export const createDeployment = (model_version_id: number) =>
  api.post<Deployment>("/deployments", { model_version_id }).then(r => r.data);
export const stopDeployment = (id: number) => api.post<Deployment>(`/deployments/${id}/stop`, {}).then(r => r.data);
```

- [ ] **Step 2: DeployPage**
```tsx
import { useEffect, useState } from "react";
import { listDeployments, createDeployment, stopDeployment, type Deployment } from "../api/client";

export function DeployPage() {
  const [items, setItems] = useState<Deployment[]>([]);
  const [mvId, setMvId] = useState("");
  const reload = () => listDeployments().then(setItems);
  useEffect(() => { reload(); const t = setInterval(reload, 3000); return () => clearInterval(t); }, []);
  return (
    <div>
      <h2>部署</h2>
      <input placeholder="model_version_id" value={mvId} onChange={e => setMvId(e.target.value)} />
      <button disabled={!mvId} onClick={() => createDeployment(Number(mvId)).then(reload)}>部署</button>
      <table><thead><tr><th>#</th><th>模型版本</th><th>状态</th><th>endpoint</th><th></th></tr></thead>
        <tbody>{items.map(d => <tr key={d.id}>
          <td>{d.id}</td><td>{d.model_version_id}</td>
          <td><b>{d.status}</b>{d.error ? ` (${d.error})` : ""}</td><td>{d.endpoint}</td>
          <td>{d.status === "running" && <button onClick={() => stopDeployment(d.id).then(reload)}>停止</button>}</td>
        </tr>)}</tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: App.tsx** — import DeployPage、增 `else if (path === "/deploy") page = <DeployPage />;`、nav 增 `<a href="/deploy">部署</a>`。

- [ ] **Step 4: 构建** `cd frontend && npm run build` → exit 0,dist/ 产出。

- [ ] **Step 5: 提交**
```bash
git add frontend/src
git commit -m "feat(frontend): deployment management page"
```

---

## 自查(Self-Review)

**Spec 覆盖(第 6.3 节部署流程):**
- 对 ModelVersion 一键部署 → Task 1/4 ✅
- model-server 从 Registry 拉权重加载 → Task 2/3 ✅
- /predict(分类/NER)、/embed(向量)、/similarity(句对)→ Task 3 ✅(按 task_type 校验)
- 停止/切换版本 → Task 4 stop(切换=部署新版本)✅
- 前端管理 → Task 5 ✅

**占位符扫描:** 无 TBD;每步含完整代码。

**类型一致性:** model-server `/load` 请求字段与 app-server `load_on_server` 发送字段一致(model_version_id/mlflow_model_name/mlflow_version/task_type);predictors 接口(predict/embed/similarity)与 main 端点调用一致;Deployment 字段在 Task 1 定义、Task 4 schema/service 使用一致;deployment_service monkeypatch 名(notify_load/notify_unload)为模块级。

**风险/前置:** model-server 与 app-server 默认端口需区分(model-server 跑 8001,app-server 8000;e2e 时 `uvicorn server.main:app --port 8001`)。model-server slow predictor 测试跨服务 import train-worker 的 recipe(同一 conda env 可行);若隔离环境不可 import,则该 slow 测试需另造模型目录——但当前单机 conda env 可行。sentence-transformers 已装。
