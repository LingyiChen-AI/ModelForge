# ModelForge Foundation Implementation Plan (阶段 1–3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭起 ModelForge 的可运行地基:基础设施、数据集与版本管理、以及 classification 任务的"训练→注册→产生模型版本"全链路。

**Architecture:** Monorepo,三个 Python 服务(app-server / train-worker / model-server)+ React 前端。app-server(FastAPI)管业务与 API,通过 Celery+Redis 投递任务给 train-worker(GPU 离线批处理),数据集快照存 MinIO,训练实验与模型注册用 MLflow。本计划只做到 classification 训练全链路,其余 task_type 与在线部署在后续计划。

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Celery, Redis, PostgreSQL, MinIO (boto3), MLflow, HuggingFace Transformers/Trainer, pytest, React+TS+Vite。

参考设计文档:`docs/superpowers/specs/2026-06-13-modelforge-architecture-design.md`

---

## 文件结构(本计划锁定)

```
ModelForge/
  docker-compose.yml                      # PG / Redis / MinIO / MLflow
  .env.example
  services/
    common/                               # 跨服务共享的常量(任务名、task_type、状态枚举)
      modelforge_common/
        __init__.py
        task_names.py                     # Celery 任务名常量
        enums.py                          # TaskType / JobStatus / DatasetKind
      pyproject.toml
    app-server/
      pyproject.toml
      app/
        main.py                           # FastAPI app 装配
        config.py                         # pydantic-settings 配置
        db.py                             # engine / session
        celery_client.py                  # 仅用于 send_task 的 Celery 客户端
        storage.py                        # MinIO 快照读写
        models/                           # SQLAlchemy ORM
          __init__.py
          base.py
          user.py
          dataset.py                      # Dataset + DatasetVersion
          training.py                     # TrainingJob + ModelVersion
        schemas/                          # Pydantic I/O 模型
          dataset.py
          training.py
        services/
          dataset_service.py              # 版本快照逻辑
          training_service.py             # 投递训练 + 同步状态
          mlflow_sync.py                  # 从 MLflow 同步 ModelVersion
        api/
          datasets.py
          training.py
          models.py
      alembic/ , alembic.ini
      tests/
    train-worker/
      pyproject.toml
      worker/
        celery_app.py                     # Celery app(注册任务)
        config.py
        storage.py                        # MinIO 读取快照
        db.py                             # 回写 job 状态
        mlflow_utils.py
        tasks.py                          # train_task 入口,按 task_type 分流
        recipes/
          __init__.py                     # get_recipe(task_type)
          base.py                         # Recipe 协议
          classification.py               # HF Trainer 分类 recipe
      tests/
    model-server/                         # 本计划只建空壳健康检查
      pyproject.toml
      server/main.py
      tests/
  frontend/
    package.json, vite 配置
    src/
      api/client.ts
      pages/DatasetsPage.tsx
      pages/DatasetDetailPage.tsx         # 版本列表
      pages/TrainingPage.tsx
      pages/ModelsPage.tsx
```

**边界说明:** `services/common` 是 app-server 与 train-worker 共享的纯常量包(任务名、枚举),避免两侧字符串漂移。app-server 只通过 `celery_client.send_task(name, args)` 投递,不 import worker 代码;worker 不 import app 代码,二者仅靠 PG + 任务名契约耦合。

---

# 阶段 1:基础设施 + 服务骨架

### Task 1: 仓库脚手架与共享常量包

**Files:**
- Create: `.gitignore`
- Create: `services/common/pyproject.toml`
- Create: `services/common/modelforge_common/__init__.py`
- Create: `services/common/modelforge_common/enums.py`
- Create: `services/common/modelforge_common/task_names.py`
- Test: `services/common/tests/test_enums.py`

- [ ] **Step 1: 写失败测试**

```python
# services/common/tests/test_enums.py
from modelforge_common.enums import TaskType, JobStatus, DatasetKind
from modelforge_common.task_names import TRAIN_TASK, EVAL_TASK

def test_task_type_values():
    assert TaskType.CLASSIFICATION.value == "classification"
    assert set(TaskType) >= {TaskType.CLASSIFICATION, TaskType.NER,
                             TaskType.PAIR, TaskType.EMBEDDING}

def test_job_status_terminal():
    assert JobStatus.SUCCEEDED.is_terminal()
    assert not JobStatus.RUNNING.is_terminal()

def test_task_names():
    assert TRAIN_TASK == "modelforge.train"
    assert EVAL_TASK == "modelforge.eval"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/common && pip install -e . && pytest -q`
Expected: FAIL — `ModuleNotFoundError: modelforge_common`

- [ ] **Step 3: 实现常量包**

```toml
# services/common/pyproject.toml
[project]
name = "modelforge-common"
version = "0.1.0"
requires-python = ">=3.10"
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
[tool.setuptools.packages.find]
where = ["."]
include = ["modelforge_common*"]
```

```python
# services/common/modelforge_common/__init__.py
```

```python
# services/common/modelforge_common/enums.py
from enum import Enum

class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    NER = "ner"
    PAIR = "pair"
    EMBEDDING = "embedding"

class DatasetKind(str, Enum):
    TRAIN = "train"
    EVAL = "eval"

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        return self in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
```

```python
# services/common/modelforge_common/task_names.py
TRAIN_TASK = "modelforge.train"
EVAL_TASK = "modelforge.eval"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services/common && pytest -q`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add .gitignore services/common
git commit -m "feat(common): shared enums and task name constants"
```

---

### Task 2: Docker Compose 基础设施

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: 写基础设施编排**

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: modelforge
      POSTGRES_PASSWORD: modelforge
      POSTGRES_DB: modelforge
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U modelforge"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7
    ports: ["6379:6379"]

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports: ["9000:9000", "9001:9001"]
    volumes: ["miniodata:/data"]

  mlflow:
    image: ghcr.io/mlflow/mlflow:v2.16.2
    depends_on: [postgres, minio]
    environment:
      MLFLOW_S3_ENDPOINT_URL: http://minio:9000
      AWS_ACCESS_KEY_ID: minioadmin
      AWS_SECRET_ACCESS_KEY: minioadmin
    command: >
      bash -c "pip install boto3 psycopg2-binary &&
      mlflow server --host 0.0.0.0 --port 5000
      --backend-store-uri postgresql://modelforge:modelforge@postgres/modelforge
      --default-artifact-root s3://mlflow/"
    ports: ["5000:5000"]

volumes:
  pgdata:
  miniodata:
```

```bash
# .env.example
DATABASE_URL=postgresql+psycopg://modelforge:modelforge@localhost:5432/modelforge
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_DATASETS=datasets
MLFLOW_TRACKING_URI=http://localhost:5000
MLFLOW_S3_ENDPOINT_URL=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
```

- [ ] **Step 2: 启动并验证**

Run: `docker compose up -d && sleep 20 && docker compose ps`
Expected: postgres / redis / minio / mlflow 全部 `running`;`curl -s localhost:5000/health` 返回 `OK`,`curl -s localhost:9000/minio/health/live` 返回 200。

- [ ] **Step 3: 创建 MinIO bucket**

Run: `docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin && docker compose exec minio mc mb -p local/datasets local/mlflow`
Expected: `Bucket created successfully`

- [ ] **Step 4: 提交**

```bash
git add docker-compose.yml .env.example
git commit -m "feat(infra): docker-compose for pg/redis/minio/mlflow"
```

---

### Task 3: app-server FastAPI 骨架 + 配置 + DB

**Files:**
- Create: `services/app-server/pyproject.toml`
- Create: `services/app-server/app/__init__.py`
- Create: `services/app-server/app/config.py`
- Create: `services/app-server/app/db.py`
- Create: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_health.py`

- [ ] **Step 1: 写失败测试**

```python
# services/app-server/tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app

def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && pip install -e . && pytest -q`
Expected: FAIL — `ModuleNotFoundError: app`

- [ ] **Step 3: 实现骨架**

```toml
# services/app-server/pyproject.toml
[project]
name = "modelforge-app-server"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  "fastapi>=0.111", "uvicorn[standard]>=0.30",
  "sqlalchemy>=2.0", "psycopg[binary]>=3.1", "alembic>=1.13",
  "pydantic-settings>=2.2", "celery>=5.3", "redis>=5.0",
  "boto3>=1.34", "mlflow>=2.16", "pandas>=2.2", "pyarrow>=16.0",
  "modelforge-common",
]
[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]
[tool.setuptools.packages.find]
include = ["app*"]
```

```python
# services/app-server/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://modelforge:modelforge@localhost:5432/modelforge"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_datasets: str = "datasets"
    mlflow_tracking_uri: str = "http://localhost:5000"

settings = Settings()
```

```python
# services/app-server/app/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

```python
# services/app-server/app/__init__.py
```

```python
# services/app-server/app/main.py
from fastapi import FastAPI

app = FastAPI(title="ModelForge app-server")

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services/app-server && pip install -e '.[dev]' && pytest -q`
Expected: PASS (1 passed)

- [ ] **Step 5: 提交**

```bash
git add services/app-server
git commit -m "feat(app-server): FastAPI skeleton with config and db session"
```

---

### Task 4: ORM Base + Alembic 初始化

**Files:**
- Create: `services/app-server/app/models/__init__.py`
- Create: `services/app-server/app/models/base.py`
- Create: `services/app-server/app/models/user.py`
- Create: `services/app-server/alembic.ini`
- Create: `services/app-server/alembic/env.py`
- Test: `services/app-server/tests/test_models_import.py`

- [ ] **Step 1: 写失败测试**

```python
# services/app-server/tests/test_models_import.py
def test_metadata_has_users_table():
    from app.models.base import Base
    import app.models  # noqa: ensure models registered
    assert "users" in Base.metadata.tables
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && pytest tests/test_models_import.py -q`
Expected: FAIL — `ModuleNotFoundError: app.models.base`

- [ ] **Step 3: 实现 Base 与 User**

```python
# services/app-server/app/models/base.py
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
```

```python
# services/app-server/app/models/user.py
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    email: Mapped[str] = mapped_column(unique=True)
    role: Mapped[str] = mapped_column(default="member")
```

```python
# services/app-server/app/models/__init__.py
from app.models.base import Base
from app.models.user import User
__all__ = ["Base", "User"]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services/app-server && pytest tests/test_models_import.py -q`
Expected: PASS

- [ ] **Step 5: 初始化 Alembic**

```ini
# services/app-server/alembic.ini  (关键行)
[alembic]
script_location = alembic
sqlalchemy.url =
```

```python
# services/app-server/alembic/env.py  (核心:用 app 的 metadata 与 settings)
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from app.config import settings
from app.models import Base
import app.models  # noqa

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

run_migrations_online()
```

> 注:用 `alembic init alembic` 生成模板后,用上面内容替换 `env.py` 的相应部分,删除 offline 分支即可。

- [ ] **Step 6: 生成并应用初版迁移(需基础设施在跑)**

Run:
```bash
cd services/app-server
alembic revision --autogenerate -m "users"
alembic upgrade head
```
Expected: 生成迁移文件;`upgrade` 后 PG 中存在 `users` 表(`psql ... -c '\dt'` 可见)。

- [ ] **Step 7: 提交**

```bash
git add services/app-server/app/models services/app-server/alembic services/app-server/alembic.ini
git commit -m "feat(app-server): ORM base, User model, alembic setup"
```

---

### Task 5: train-worker Celery 骨架

**Files:**
- Create: `services/train-worker/pyproject.toml`
- Create: `services/train-worker/worker/__init__.py`
- Create: `services/train-worker/worker/config.py`
- Create: `services/train-worker/worker/celery_app.py`
- Create: `services/train-worker/worker/tasks.py`
- Test: `services/train-worker/tests/test_celery_app.py`

- [ ] **Step 1: 写失败测试**

```python
# services/train-worker/tests/test_celery_app.py
from worker.celery_app import celery_app
from modelforge_common.task_names import TRAIN_TASK

def test_train_task_registered():
    assert TRAIN_TASK in celery_app.tasks
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/train-worker && pip install -e . && pytest -q`
Expected: FAIL — `ModuleNotFoundError: worker.celery_app`

- [ ] **Step 3: 实现骨架**

```toml
# services/train-worker/pyproject.toml
[project]
name = "modelforge-train-worker"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  "celery>=5.3", "redis>=5.0", "sqlalchemy>=2.0", "psycopg[binary]>=3.1",
  "boto3>=1.34", "mlflow>=2.16", "pandas>=2.2", "pyarrow>=16.0",
  "transformers>=4.44", "datasets>=2.20", "torch>=2.2",
  "scikit-learn>=1.5", "modelforge-common",
]
[project.optional-dependencies]
dev = ["pytest>=8.0"]
[tool.setuptools.packages.find]
include = ["worker*"]
```

```python
# services/train-worker/worker/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://modelforge:modelforge@localhost:5432/modelforge"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_datasets: str = "datasets"
    mlflow_tracking_uri: str = "http://localhost:5000"

settings = Settings()
```

```python
# services/train-worker/worker/celery_app.py
from celery import Celery
from worker.config import settings

celery_app = Celery("modelforge", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_track_started = True
celery_app.conf.worker_prefetch_multiplier = 1  # 一次只取一个 GPU 任务

import worker.tasks  # noqa: 注册任务
```

```python
# services/train-worker/worker/__init__.py
```

```python
# services/train-worker/worker/tasks.py
from worker.celery_app import celery_app
from modelforge_common.task_names import TRAIN_TASK

@celery_app.task(name=TRAIN_TASK, bind=True)
def train_task(self, training_job_id: int):
    # 实际实现见 Task 10
    raise NotImplementedError
```

> 注意 `celery_app.py` 末尾 import `tasks`,而 `tasks.py` import `celery_app` —— 为避免循环 import,`tasks.py` 只从 `celery_app` 取 `celery_app` 对象,且 import 放在模块顶部即可(Celery 标准用法)。

- [ ] **Step 4: 运行确认通过**

Run: `cd services/train-worker && pip install -e '.[dev]' && pytest -q`
Expected: PASS (1 passed)

- [ ] **Step 5: 提交**

```bash
git add services/train-worker
git commit -m "feat(train-worker): celery skeleton with registered train task"
```

---

### Task 6: model-server 空壳 + 前端脚手架

**Files:**
- Create: `services/model-server/pyproject.toml`
- Create: `services/model-server/server/main.py`
- Test: `services/model-server/tests/test_health.py`
- Create: `frontend/` (Vite React TS)

- [ ] **Step 1: 写 model-server 失败测试**

```python
# services/model-server/tests/test_health.py
from fastapi.testclient import TestClient
from server.main import app

def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/model-server && pip install -e '.[dev]' && pytest -q`
Expected: FAIL — `ModuleNotFoundError: server.main`

- [ ] **Step 3: 实现 model-server 空壳**

```toml
# services/model-server/pyproject.toml
[project]
name = "modelforge-model-server"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["fastapi>=0.111", "uvicorn[standard]>=0.30", "mlflow>=2.16",
  "transformers>=4.44", "torch>=2.2"]
[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]
[tool.setuptools.packages.find]
include = ["server*"]
```

```python
# services/model-server/server/main.py
from fastapi import FastAPI
app = FastAPI(title="ModelForge model-server")

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 4: 运行确认通过 + 初始化前端**

Run:
```bash
cd services/model-server && pytest -q          # PASS
cd ../../ && npm create vite@latest frontend -- --template react-ts
cd frontend && npm install && npm install @tanstack/react-query axios && npm run build
```
Expected: model-server 测试 PASS;前端 `npm run build` 成功产出 `dist/`。

- [ ] **Step 5: 提交**

```bash
git add services/model-server frontend
git commit -m "feat: model-server health stub and react frontend scaffold"
```

---

# 阶段 2:数据集与版本管理

### Task 7: Dataset / DatasetVersion 模型 + 迁移

**Files:**
- Create: `services/app-server/app/models/dataset.py`
- Modify: `services/app-server/app/models/__init__.py`
- Test: `services/app-server/tests/test_dataset_model.py`

- [ ] **Step 1: 写失败测试**

```python
# services/app-server/tests/test_dataset_model.py
from app.models.base import Base
import app.models  # noqa

def test_dataset_tables_registered():
    assert "datasets" in Base.metadata.tables
    assert "dataset_versions" in Base.metadata.tables
    cols = Base.metadata.tables["dataset_versions"].columns.keys()
    assert {"id", "dataset_id", "version_no", "storage_uri",
            "row_count", "checksum", "stats", "note"} <= set(cols)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && pytest tests/test_dataset_model.py -q`
Expected: FAIL — `KeyError: 'datasets'`

- [ ] **Step 3: 实现模型**

```python
# services/app-server/app/models/dataset.py
from sqlalchemy import ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class Dataset(Base, TimestampMixin):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    kind: Mapped[str] = mapped_column()        # DatasetKind
    task_type: Mapped[str] = mapped_column()   # TaskType
    schema_: Mapped[dict] = mapped_column("schema", JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    versions: Mapped[list["DatasetVersion"]] = relationship(back_populates="dataset")

class DatasetVersion(Base, TimestampMixin):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    version_no: Mapped[int] = mapped_column()
    storage_uri: Mapped[str] = mapped_column()
    row_count: Mapped[int] = mapped_column()
    checksum: Mapped[str] = mapped_column()
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(default="")
    dataset: Mapped["Dataset"] = relationship(back_populates="versions")
```

```python
# services/app-server/app/models/__init__.py
from app.models.base import Base
from app.models.user import User
from app.models.dataset import Dataset, DatasetVersion
__all__ = ["Base", "User", "Dataset", "DatasetVersion"]
```

- [ ] **Step 4: 运行确认通过 + 生成迁移**

Run:
```bash
cd services/app-server && pytest tests/test_dataset_model.py -q   # PASS
alembic revision --autogenerate -m "datasets" && alembic upgrade head
```
Expected: 测试 PASS;PG 中出现 `datasets`、`dataset_versions` 表。

- [ ] **Step 5: 提交**

```bash
git add services/app-server/app/models
git commit -m "feat(app-server): Dataset and DatasetVersion models"
```

---

### Task 8: MinIO 快照存储服务

**Files:**
- Create: `services/app-server/app/storage.py`
- Test: `services/app-server/tests/test_storage.py`

- [ ] **Step 1: 写失败测试(用 moto 模拟 S3)**

```python
# services/app-server/tests/test_storage.py
import io, pandas as pd
import boto3, pytest
from moto import mock_aws
from app.storage import SnapshotStorage

@mock_aws
def test_write_and_read_snapshot_roundtrip():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="datasets")
    store = SnapshotStorage(endpoint_url=None, access_key="x", secret_key="y",
                            bucket="datasets")
    df = pd.DataFrame({"text": ["a", "b"], "label": ["x", "y"]})
    uri, checksum, rows = store.write_snapshot(dataset_id=1, version_no=1, df=df)
    assert uri.startswith("s3://datasets/dataset=1/v1/")
    assert rows == 2 and len(checksum) == 64
    back = store.read_snapshot(uri)
    assert back.equals(df)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && pip install moto && pytest tests/test_storage.py -q`
Expected: FAIL — `ModuleNotFoundError: app.storage`

- [ ] **Step 3: 实现存储服务**

```python
# services/app-server/app/storage.py
import hashlib, io
import boto3, pandas as pd

class SnapshotStorage:
    def __init__(self, endpoint_url, access_key, secret_key, bucket):
        self.bucket = bucket
        self.s3 = boto3.client(
            "s3", endpoint_url=endpoint_url,
            aws_access_key_id=access_key, aws_secret_access_key=secret_key,
            region_name="us-east-1")

    def write_snapshot(self, dataset_id: int, version_no: int, df: pd.DataFrame):
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        data = buf.getvalue()
        checksum = hashlib.sha256(data).hexdigest()
        key = f"dataset={dataset_id}/v{version_no}/data.parquet"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data)
        return f"s3://{self.bucket}/{key}", checksum, len(df)

    def read_snapshot(self, uri: str) -> pd.DataFrame:
        key = uri.split(f"s3://{self.bucket}/", 1)[1]
        obj = self.s3.get_object(Bucket=self.bucket, Key=key)
        return pd.read_parquet(io.BytesIO(obj["Body"].read()))

def build_storage() -> "SnapshotStorage":
    from app.config import settings
    return SnapshotStorage(settings.s3_endpoint_url, settings.s3_access_key,
                           settings.s3_secret_key, settings.s3_bucket_datasets)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services/app-server && pytest tests/test_storage.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/app-server/app/storage.py
git commit -m "feat(app-server): MinIO snapshot storage with checksum"
```

---

### Task 9: 数据集版本服务 + schema 校验

**Files:**
- Create: `services/app-server/app/schemas/dataset.py`
- Create: `services/app-server/app/services/dataset_service.py`
- Test: `services/app-server/tests/test_dataset_service.py`

- [ ] **Step 1: 写失败测试**

```python
# services/app-server/tests/test_dataset_service.py
import pandas as pd, pytest
from app.services.dataset_service import validate_rows, REQUIRED_COLUMNS
from modelforge_common.enums import TaskType

def test_required_columns_classification():
    assert REQUIRED_COLUMNS[TaskType.CLASSIFICATION] == ["text", "label"]

def test_validate_rows_ok():
    df = pd.DataFrame({"text": ["a"], "label": ["x"]})
    validate_rows(df, TaskType.CLASSIFICATION)  # 不抛异常

def test_validate_rows_missing_column():
    df = pd.DataFrame({"text": ["a"]})
    with pytest.raises(ValueError, match="missing columns"):
        validate_rows(df, TaskType.CLASSIFICATION)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && pytest tests/test_dataset_service.py -q`
Expected: FAIL — `ModuleNotFoundError: app.services.dataset_service`

- [ ] **Step 3: 实现 schema + 校验 + 版本创建**

```python
# services/app-server/app/schemas/dataset.py
from pydantic import BaseModel
from modelforge_common.enums import TaskType, DatasetKind

class DatasetCreate(BaseModel):
    name: str
    kind: DatasetKind
    task_type: TaskType

class DatasetOut(BaseModel):
    id: int
    name: str
    kind: str
    task_type: str
    class Config: from_attributes = True

class DatasetVersionOut(BaseModel):
    id: int
    dataset_id: int
    version_no: int
    storage_uri: str
    row_count: int
    checksum: str
    note: str
    class Config: from_attributes = True
```

```python
# services/app-server/app/services/dataset_service.py
import pandas as pd
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from modelforge_common.enums import TaskType
from app.models.dataset import Dataset, DatasetVersion
from app.storage import SnapshotStorage

REQUIRED_COLUMNS = {
    TaskType.CLASSIFICATION: ["text", "label"],
    TaskType.NER: ["tokens", "tags"],
    TaskType.PAIR: ["text_a", "text_b"],
    TaskType.EMBEDDING: ["query", "pos"],
}

def validate_rows(df: pd.DataFrame, task_type: TaskType) -> None:
    required = REQUIRED_COLUMNS[task_type]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns for {task_type.value}: {missing}")
    if len(df) == 0:
        raise ValueError("dataset is empty")

def create_version(db: Session, store: SnapshotStorage, dataset: Dataset,
                   df: pd.DataFrame, note: str = "") -> DatasetVersion:
    validate_rows(df, TaskType(dataset.task_type))
    next_no = (db.execute(
        select(func.coalesce(func.max(DatasetVersion.version_no), 0))
        .where(DatasetVersion.dataset_id == dataset.id)).scalar()) + 1
    uri, checksum, rows = store.write_snapshot(dataset.id, next_no, df)
    version = DatasetVersion(
        dataset_id=dataset.id, version_no=next_no, storage_uri=uri,
        row_count=rows, checksum=checksum, note=note,
        stats={"columns": list(df.columns)})
    db.add(version)
    db.commit()
    db.refresh(version)
    return version
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services/app-server && pytest tests/test_dataset_service.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: 提交**

```bash
git add services/app-server/app/schemas/dataset.py services/app-server/app/services/dataset_service.py
git commit -m "feat(app-server): dataset version service with schema validation"
```

---

### Task 10: 数据集 API(CRUD + 上传建版本 + 版本列表)

**Files:**
- Create: `services/app-server/app/api/datasets.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_datasets_api.py`

- [ ] **Step 1: 写失败测试(用 SQLite + moto,覆盖 create→upload→list)**

```python
# services/app-server/tests/test_datasets_api.py
import io, pandas as pd, boto3
from moto import mock_aws
from fastapi.testclient import TestClient

@mock_aws
def test_dataset_create_upload_list(monkeypatch, tmp_path):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="datasets")
    from app.db import engine
    from sqlalchemy import create_engine
    test_engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    from app.models import Base
    Base.metadata.create_all(test_engine)
    from app import db as dbmod
    from sqlalchemy.orm import sessionmaker
    dbmod.SessionLocal = sessionmaker(bind=test_engine, expire_on_commit=False)

    from app.main import app
    client = TestClient(app)

    r = client.post("/datasets", json={"name": "d1", "kind": "train",
                                        "task_type": "classification"})
    assert r.status_code == 201
    ds_id = r.json()["id"]

    df = pd.DataFrame({"text": ["a", "b"], "label": ["x", "y"]})
    buf = io.BytesIO(); df.to_csv(buf, index=False); buf.seek(0)
    r = client.post(f"/datasets/{ds_id}/versions",
                    files={"file": ("d.csv", buf, "text/csv")})
    assert r.status_code == 201
    assert r.json()["version_no"] == 1 and r.json()["row_count"] == 2

    r = client.get(f"/datasets/{ds_id}/versions")
    assert len(r.json()) == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && pytest tests/test_datasets_api.py -q`
Expected: FAIL — 路由 `/datasets` 不存在(404)

- [ ] **Step 3: 实现 API + 装配路由**

```python
# services/app-server/app/api/datasets.py
import io, pandas as pd
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.storage import build_storage
from app.models.dataset import Dataset, DatasetVersion
from app.schemas.dataset import DatasetCreate, DatasetOut, DatasetVersionOut
from app.services.dataset_service import create_version

router = APIRouter(prefix="/datasets", tags=["datasets"])

@router.post("", response_model=DatasetOut, status_code=201)
def create_dataset(body: DatasetCreate, db: Session = Depends(get_db)):
    ds = Dataset(name=body.name, kind=body.kind.value, task_type=body.task_type.value)
    db.add(ds); db.commit(); db.refresh(ds)
    return ds

@router.get("", response_model=list[DatasetOut])
def list_datasets(db: Session = Depends(get_db)):
    return db.execute(select(Dataset)).scalars().all()

def _read_upload(file: UploadFile) -> pd.DataFrame:
    raw = file.file.read()
    if file.filename.endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw))
    if file.filename.endswith(".jsonl"):
        return pd.read_json(io.BytesIO(raw), lines=True)
    raise HTTPException(400, "only .csv or .jsonl supported")

@router.post("/{dataset_id}/versions", response_model=DatasetVersionOut, status_code=201)
def upload_version(dataset_id: int, file: UploadFile = File(...),
                   note: str = "", db: Session = Depends(get_db)):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "dataset not found")
    df = _read_upload(file)
    try:
        return create_version(db, build_storage(), ds, df, note)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("/{dataset_id}/versions", response_model=list[DatasetVersionOut])
def list_versions(dataset_id: int, db: Session = Depends(get_db)):
    return db.execute(select(DatasetVersion)
                      .where(DatasetVersion.dataset_id == dataset_id)
                      .order_by(DatasetVersion.version_no.desc())).scalars().all()
```

```python
# services/app-server/app/main.py  (追加)
from app.api import datasets
app.include_router(datasets.router)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services/app-server && pytest tests/test_datasets_api.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/app-server/app/api/datasets.py services/app-server/app/main.py
git commit -m "feat(app-server): dataset CRUD, version upload and listing API"
```

---

### Task 11: 前端数据集页面

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/DatasetsPage.tsx`
- Create: `frontend/src/pages/DatasetDetailPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: API client**

```ts
// frontend/src/api/client.ts
import axios from "axios";
export const api = axios.create({ baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000" });

export type Dataset = { id: number; name: string; kind: string; task_type: string };
export type DatasetVersion = { id: number; version_no: number; row_count: number; checksum: string; note: string };

export const listDatasets = () => api.get<Dataset[]>("/datasets").then(r => r.data);
export const createDataset = (b: { name: string; kind: string; task_type: string }) =>
  api.post<Dataset>("/datasets", b).then(r => r.data);
export const listVersions = (id: number) =>
  api.get<DatasetVersion[]>(`/datasets/${id}/versions`).then(r => r.data);
export const uploadVersion = (id: number, file: File, note: string) => {
  const fd = new FormData(); fd.append("file", file); fd.append("note", note);
  return api.post<DatasetVersion>(`/datasets/${id}/versions`, fd).then(r => r.data);
};
```

- [ ] **Step 2: 数据集列表/创建页**

```tsx
// frontend/src/pages/DatasetsPage.tsx
import { useEffect, useState } from "react";
import { listDatasets, createDataset, Dataset } from "../api/client";

export function DatasetsPage() {
  const [items, setItems] = useState<Dataset[]>([]);
  const [name, setName] = useState("");
  const reload = () => listDatasets().then(setItems);
  useEffect(() => { reload(); }, []);
  return (
    <div>
      <h2>数据集</h2>
      <div>
        <input value={name} onChange={e => setName(e.target.value)} placeholder="名称" />
        <button onClick={() => createDataset({ name, kind: "train", task_type: "classification" }).then(reload)}>
          新建(分类训练集)
        </button>
      </div>
      <ul>
        {items.map(d => <li key={d.id}><a href={`/datasets/${d.id}`}>{d.name}</a> — {d.task_type}</li>)}
      </ul>
    </div>
  );
}
```

- [ ] **Step 3: 数据集详情/版本页**

```tsx
// frontend/src/pages/DatasetDetailPage.tsx
import { useEffect, useState } from "react";
import { listVersions, uploadVersion, DatasetVersion } from "../api/client";

export function DatasetDetailPage({ id }: { id: number }) {
  const [versions, setVersions] = useState<DatasetVersion[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const reload = () => listVersions(id).then(setVersions);
  useEffect(() => { reload(); }, [id]);
  return (
    <div>
      <h2>版本</h2>
      <input type="file" accept=".csv,.jsonl" onChange={e => setFile(e.target.files?.[0] ?? null)} />
      <button disabled={!file} onClick={() => file && uploadVersion(id, file, "").then(reload)}>上传新版本</button>
      <table><thead><tr><th>版本</th><th>行数</th><th>checksum</th></tr></thead>
        <tbody>{versions.map(v => <tr key={v.id}><td>v{v.version_no}</td><td>{v.row_count}</td><td>{v.checksum.slice(0,12)}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: 路由装配并构建**

```tsx
// frontend/src/App.tsx  (最小手写路由,避免引入额外依赖)
import { DatasetsPage } from "./pages/DatasetsPage";
import { DatasetDetailPage } from "./pages/DatasetDetailPage";

export default function App() {
  const m = window.location.pathname.match(/^\/datasets\/(\d+)$/);
  if (m) return <DatasetDetailPage id={Number(m[1])} />;
  return <DatasetsPage />;
}
```

Run: `cd frontend && npm run build`
Expected: 构建成功。手动验证:`npm run dev`,在 app-server (`uvicorn app.main:app`) 运行下创建数据集并上传 CSV,版本出现在列表。

- [ ] **Step 5: 提交**

```bash
git add frontend/src
git commit -m "feat(frontend): datasets list/detail pages with version upload"
```

---

# 阶段 3:classification 训练全链路

### Task 12: TrainingJob / ModelVersion 模型 + 迁移

**Files:**
- Create: `services/app-server/app/models/training.py`
- Modify: `services/app-server/app/models/__init__.py`
- Test: `services/app-server/tests/test_training_model.py`

- [ ] **Step 1: 写失败测试**

```python
# services/app-server/tests/test_training_model.py
from app.models.base import Base
import app.models  # noqa

def test_training_tables():
    assert "training_jobs" in Base.metadata.tables
    assert "model_versions" in Base.metadata.tables
    cols = Base.metadata.tables["training_jobs"].columns.keys()
    assert {"dataset_version_id", "base_model", "task_type", "hyperparams",
            "status", "celery_task_id", "mlflow_run_id", "error"} <= set(cols)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && pytest tests/test_training_model.py -q`
Expected: FAIL — `KeyError: 'training_jobs'`

- [ ] **Step 3: 实现模型**

```python
# services/app-server/app/models/training.py
from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin
from modelforge_common.enums import JobStatus

class TrainingJob(Base, TimestampMixin):
    __tablename__ = "training_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"))
    base_model: Mapped[str] = mapped_column()
    task_type: Mapped[str] = mapped_column()
    hyperparams: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(default=JobStatus.PENDING.value)
    celery_task_id: Mapped[str | None] = mapped_column(nullable=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(nullable=True)

class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    source_training_job_id: Mapped[int] = mapped_column(ForeignKey("training_jobs.id"))
    mlflow_model_name: Mapped[str] = mapped_column()
    mlflow_version: Mapped[str] = mapped_column()
    task_type: Mapped[str] = mapped_column()
    base_model: Mapped[str] = mapped_column()
    train_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    stage: Mapped[str] = mapped_column(default="none")
    artifact_uri: Mapped[str | None] = mapped_column(nullable=True)
```

```python
# services/app-server/app/models/__init__.py
from app.models.base import Base
from app.models.user import User
from app.models.dataset import Dataset, DatasetVersion
from app.models.training import TrainingJob, ModelVersion
__all__ = ["Base", "User", "Dataset", "DatasetVersion", "TrainingJob", "ModelVersion"]
```

- [ ] **Step 4: 运行确认通过 + 迁移**

Run:
```bash
cd services/app-server && pytest tests/test_training_model.py -q   # PASS
alembic revision --autogenerate -m "training_jobs and model_versions" && alembic upgrade head
```
Expected: PASS;PG 出现两张新表。

- [ ] **Step 5: 提交**

```bash
git add services/app-server/app/models
git commit -m "feat(app-server): TrainingJob and ModelVersion models"
```

---

### Task 13: 训练任务投递 API

**Files:**
- Create: `services/app-server/app/celery_client.py`
- Create: `services/app-server/app/schemas/training.py`
- Create: `services/app-server/app/services/training_service.py`
- Create: `services/app-server/app/api/training.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_training_api.py`

- [ ] **Step 1: 写失败测试(mock celery send_task)**

```python
# services/app-server/tests/test_training_api.py
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

def test_create_training_job(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    eng = create_engine(f"sqlite:///{tmp_path}/t.db"); Base.metadata.create_all(eng)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    # 准备一个 dataset_version
    from app.models.dataset import Dataset, DatasetVersion
    s = dbmod.SessionLocal()
    ds = Dataset(name="d", kind="train", task_type="classification"); s.add(ds); s.commit()
    dv = DatasetVersion(dataset_id=ds.id, version_no=1, storage_uri="s3://x/y",
                        row_count=2, checksum="c", note=""); s.add(dv); s.commit()
    dv_id = dv.id; s.close()

    sent = {}
    import app.services.training_service as ts
    monkeypatch.setattr(ts, "send_train_task",
                        lambda job_id: sent.setdefault("job", job_id) or "celery-123")

    from app.main import app
    client = TestClient(app)
    r = client.post("/training-jobs", json={
        "name": "job1", "dataset_version_id": dv_id,
        "base_model": "bert-base-chinese", "task_type": "classification",
        "hyperparams": {"epochs": 1}})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["celery_task_id"] == "celery-123"
    assert sent["job"] == body["id"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && pytest tests/test_training_api.py -q`
Expected: FAIL — 路由不存在

- [ ] **Step 3: 实现 celery client + service + api**

```python
# services/app-server/app/celery_client.py
from celery import Celery
from app.config import settings
from modelforge_common.task_names import TRAIN_TASK

_celery = Celery("modelforge-client", broker=settings.redis_url)

def send_train_task(training_job_id: int) -> str:
    result = _celery.send_task(TRAIN_TASK, args=[training_job_id])
    return result.id
```

```python
# services/app-server/app/schemas/training.py
from pydantic import BaseModel
from modelforge_common.enums import TaskType

class TrainingJobCreate(BaseModel):
    name: str
    dataset_version_id: int
    base_model: str
    task_type: TaskType
    hyperparams: dict = {}

class TrainingJobOut(BaseModel):
    id: int
    name: str
    status: str
    celery_task_id: str | None
    mlflow_run_id: str | None
    error: str | None
    class Config: from_attributes = True
```

```python
# services/app-server/app/services/training_service.py
from sqlalchemy.orm import Session
from app.models.training import TrainingJob
from app.models.dataset import DatasetVersion
from app.celery_client import send_train_task   # re-exported for monkeypatch in tests

def create_and_dispatch(db: Session, body) -> TrainingJob:
    dv = db.get(DatasetVersion, body.dataset_version_id)
    if not dv:
        raise ValueError("dataset_version not found")
    job = TrainingJob(name=body.name, dataset_version_id=body.dataset_version_id,
                      base_model=body.base_model, task_type=body.task_type.value,
                      hyperparams=body.hyperparams)
    db.add(job); db.commit(); db.refresh(job)
    job.celery_task_id = send_train_task(job.id)
    db.commit(); db.refresh(job)
    return job
```

```python
# services/app-server/app/api/training.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.training import TrainingJob
from app.schemas.training import TrainingJobCreate, TrainingJobOut
from app.services import training_service

router = APIRouter(prefix="/training-jobs", tags=["training"])

@router.post("", response_model=TrainingJobOut, status_code=201)
def create(body: TrainingJobCreate, db: Session = Depends(get_db)):
    try:
        return training_service.create_and_dispatch(db, body)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[TrainingJobOut])
def list_jobs(db: Session = Depends(get_db)):
    return db.execute(select(TrainingJob).order_by(TrainingJob.id.desc())).scalars().all()

@router.get("/{job_id}", response_model=TrainingJobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, "not found")
    return job
```

```python
# services/app-server/app/main.py  (追加)
from app.api import training
app.include_router(training.router)
```

> 注:test 中 monkeypatch 的是 `training_service.send_train_task`,因此 service 里用 `from app.celery_client import send_train_task` 并以模块属性方式调用(`send_train_task(...)`)即可被替换。

- [ ] **Step 4: 运行确认通过**

Run: `cd services/app-server && pytest tests/test_training_api.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/app-server/app/celery_client.py services/app-server/app/schemas/training.py services/app-server/app/services/training_service.py services/app-server/app/api/training.py services/app-server/app/main.py
git commit -m "feat(app-server): training job dispatch API"
```

---

### Task 14: worker 端 DB 回写 + 状态更新工具

**Files:**
- Create: `services/train-worker/worker/db.py`
- Test: `services/train-worker/tests/test_db_status.py`

- [ ] **Step 1: 写失败测试(SQLite + 原生 SQL,worker 不依赖 app 的 ORM)**

```python
# services/train-worker/tests/test_db_status.py
from sqlalchemy import create_engine, text
from worker.db import set_job_status, JobStatus

def test_set_job_status(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE training_jobs (id INTEGER PRIMARY KEY, "
                       "status TEXT, mlflow_run_id TEXT, error TEXT)"))
        c.execute(text("INSERT INTO training_jobs (id, status) VALUES (1, 'pending')"))
    set_job_status(eng, 1, JobStatus.RUNNING)
    with eng.connect() as c:
        assert c.execute(text("SELECT status FROM training_jobs WHERE id=1")).scalar() == "running"
    set_job_status(eng, 1, JobStatus.FAILED, error="boom")
    with eng.connect() as c:
        row = c.execute(text("SELECT status, error FROM training_jobs WHERE id=1")).one()
        assert row.status == "failed" and row.error == "boom"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/train-worker && pytest tests/test_db_status.py -q`
Expected: FAIL — `ModuleNotFoundError: worker.db`

- [ ] **Step 3: 实现**

```python
# services/train-worker/worker/db.py
from sqlalchemy import create_engine, text, Engine
from modelforge_common.enums import JobStatus
from worker.config import settings

def build_engine() -> Engine:
    return create_engine(settings.database_url, pool_pre_ping=True)

def set_job_status(engine: Engine, job_id: int, status: JobStatus,
                   mlflow_run_id: str | None = None, error: str | None = None) -> None:
    sets = ["status = :status"]
    params = {"status": status.value, "id": job_id}
    if mlflow_run_id is not None:
        sets.append("mlflow_run_id = :mrid"); params["mrid"] = mlflow_run_id
    if error is not None:
        sets.append("error = :err"); params["err"] = error
    with engine.begin() as c:
        c.execute(text(f"UPDATE training_jobs SET {', '.join(sets)} WHERE id = :id"), params)

def load_job(engine: Engine, job_id: int) -> dict:
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT j.id, j.base_model, j.task_type, j.hyperparams, j.name, "
            "v.storage_uri FROM training_jobs j "
            "JOIN dataset_versions v ON v.id = j.dataset_version_id "
            "WHERE j.id = :id"), {"id": job_id}).mappings().one()
        return dict(row)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services/train-worker && pytest tests/test_db_status.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/train-worker/worker/db.py
git commit -m "feat(train-worker): job status writeback helpers"
```

---

### Task 15: worker 存储读取 + classification recipe

**Files:**
- Create: `services/train-worker/worker/storage.py`
- Create: `services/train-worker/worker/recipes/__init__.py`
- Create: `services/train-worker/worker/recipes/base.py`
- Create: `services/train-worker/worker/recipes/classification.py`
- Test: `services/train-worker/tests/test_classification_recipe.py`

- [ ] **Step 1: 写失败测试(用极小数据 + tiny 模型跑真实训练冒烟)**

```python
# services/train-worker/tests/test_classification_recipe.py
import pandas as pd, pytest
from worker.recipes import get_recipe
from worker.recipes.classification import ClassificationRecipe

def test_get_recipe_classification():
    assert isinstance(get_recipe("classification"), ClassificationRecipe)

@pytest.mark.slow
def test_classification_trains_and_returns_metrics(tmp_path):
    df = pd.DataFrame({"text": ["good", "bad", "great", "awful"] * 4,
                       "label": ["pos", "neg", "pos", "neg"] * 4})
    recipe = ClassificationRecipe()
    result = recipe.train(
        df=df, base_model="prajjwal1/bert-tiny",
        hyperparams={"epochs": 1, "batch_size": 4, "max_length": 16},
        output_dir=str(tmp_path))
    assert "accuracy" in result.metrics
    assert result.label_names == ["neg", "pos"]
    assert (tmp_path / "label_map.json").exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/train-worker && pytest tests/test_classification_recipe.py -q`
Expected: FAIL — `ModuleNotFoundError: worker.recipes`

- [ ] **Step 3: 实现 storage + recipe**

```python
# services/train-worker/worker/storage.py
import io, boto3, pandas as pd
from worker.config import settings

def _client():
    return boto3.client("s3", endpoint_url=settings.s3_endpoint_url,
                        aws_access_key_id=settings.s3_access_key,
                        aws_secret_access_key=settings.s3_secret_key,
                        region_name="us-east-1")

def read_snapshot(uri: str) -> pd.DataFrame:
    _, _, rest = uri.partition("s3://")
    bucket, _, key = rest.partition("/")
    obj = _client().get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(io.BytesIO(obj["Body"].read()))
```

```python
# services/train-worker/worker/recipes/base.py
from dataclasses import dataclass, field

@dataclass
class TrainResult:
    metrics: dict
    artifact_dir: str
    label_names: list[str] = field(default_factory=list)

class Recipe:
    def train(self, df, base_model, hyperparams, output_dir) -> TrainResult:
        raise NotImplementedError
```

```python
# services/train-worker/worker/recipes/classification.py
import json, os
import numpy as np
from datasets import Dataset as HFDataset
from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                          TrainingArguments, Trainer)
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from worker.recipes.base import Recipe, TrainResult

class ClassificationRecipe(Recipe):
    def train(self, df, base_model, hyperparams, output_dir) -> TrainResult:
        labels = sorted(df["label"].unique().tolist())
        label2id = {l: i for i, l in enumerate(labels)}
        df = df.assign(_y=df["label"].map(label2id))
        max_len = int(hyperparams.get("max_length", 128))

        tok = AutoTokenizer.from_pretrained(base_model)
        def tok_fn(b): return tok(b["text"], truncation=True, max_length=max_len)
        hf = HFDataset.from_pandas(df[["text", "_y"]].rename(columns={"_y": "labels"}))
        hf = hf.map(tok_fn, batched=True)

        model = AutoModelForSequenceClassification.from_pretrained(
            base_model, num_labels=len(labels),
            id2label={i: l for l, i in label2id.items()}, label2id=label2id)

        def metrics_fn(eval_pred):
            logits, y = eval_pred
            pred = np.argmax(logits, axis=-1)
            p, r, f1, _ = precision_recall_fscore_support(y, pred, average="macro", zero_division=0)
            return {"accuracy": accuracy_score(y, pred), "precision": p, "recall": r, "f1": f1}

        args = TrainingArguments(
            output_dir=output_dir, num_train_epochs=int(hyperparams.get("epochs", 3)),
            per_device_train_batch_size=int(hyperparams.get("batch_size", 16)),
            per_device_eval_batch_size=int(hyperparams.get("batch_size", 16)),
            learning_rate=float(hyperparams.get("lr", 5e-5)),
            report_to=[], logging_steps=10, save_strategy="no")
        trainer = Trainer(model=model, args=args, train_dataset=hf, eval_dataset=hf,
                          compute_metrics=metrics_fn)
        trainer.train()
        metrics = trainer.evaluate()
        metrics = {k.replace("eval_", ""): v for k, v in metrics.items()}

        trainer.save_model(output_dir)
        tok.save_pretrained(output_dir)
        with open(os.path.join(output_dir, "label_map.json"), "w") as f:
            json.dump(label2id, f)
        return TrainResult(metrics=metrics, artifact_dir=output_dir, label_names=labels)
```

```python
# services/train-worker/worker/recipes/__init__.py
from worker.recipes.base import Recipe
from worker.recipes.classification import ClassificationRecipe

def get_recipe(task_type: str) -> Recipe:
    if task_type == "classification":
        return ClassificationRecipe()
    raise NotImplementedError(f"recipe for {task_type} not implemented yet")
```

- [ ] **Step 4: 运行确认通过(含真实冒烟训练)**

Run: `cd services/train-worker && pytest tests/test_classification_recipe.py -q -m slow`
Expected: PASS(首次会下载 `prajjwal1/bert-tiny`,需联网;之后 accuracy 字段存在,label_map.json 生成)。

- [ ] **Step 5: 提交**

```bash
git add services/train-worker/worker/storage.py services/train-worker/worker/recipes
git commit -m "feat(train-worker): snapshot reader and classification recipe"
```

---

### Task 16: MLflow 记录 + train_task 串联全链路

**Files:**
- Create: `services/train-worker/worker/mlflow_utils.py`
- Modify: `services/train-worker/worker/tasks.py`
- Test: `services/train-worker/tests/test_train_task.py`

- [ ] **Step 1: 写失败测试(打桩 recipe / mlflow / storage,验证编排与状态流转)**

```python
# services/train-worker/tests/test_train_task.py
from sqlalchemy import create_engine, text
import pandas as pd, worker.tasks as tasks
from worker.recipes.base import TrainResult

def test_train_task_orchestration(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE training_jobs (id INTEGER PRIMARY KEY, name TEXT, "
                       "base_model TEXT, task_type TEXT, hyperparams TEXT, status TEXT, "
                       "dataset_version_id INTEGER, mlflow_run_id TEXT, error TEXT)"))
        c.execute(text("CREATE TABLE dataset_versions (id INTEGER PRIMARY KEY, storage_uri TEXT)"))
        c.execute(text("INSERT INTO dataset_versions (id, storage_uri) VALUES (1,'s3://b/k')"))
        c.execute(text("INSERT INTO training_jobs (id,name,base_model,task_type,hyperparams,"
                       "status,dataset_version_id) VALUES (1,'j','m','classification','{}','pending',1)"))

    monkeypatch.setattr(tasks, "build_engine", lambda: eng)
    monkeypatch.setattr(tasks, "read_snapshot",
                        lambda uri: pd.DataFrame({"text": ["a"], "label": ["x"]}))
    fake = TrainResult(metrics={"accuracy": 1.0}, artifact_dir=str(tmp_path), label_names=["x"])
    monkeypatch.setattr(tasks, "run_recipe", lambda *a, **k: fake)
    captured = {}
    monkeypatch.setattr(tasks, "log_and_register",
                        lambda **k: captured.update(k) or ("run-1", "ModelForge-1", "3"))

    tasks.train_task.run(training_job_id=1)

    with eng.connect() as c:
        row = c.execute(text("SELECT status, mlflow_run_id FROM training_jobs WHERE id=1")).one()
    assert row.status == "succeeded" and row.mlflow_run_id == "run-1"
    assert captured["metrics"] == {"accuracy": 1.0}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/train-worker && pytest tests/test_train_task.py -q`
Expected: FAIL — `tasks.train_task` 抛 `NotImplementedError` / 缺少 `build_engine` 等符号

- [ ] **Step 3: 实现 mlflow_utils 与编排**

```python
# services/train-worker/worker/mlflow_utils.py
import mlflow
from worker.config import settings

def log_and_register(*, job_name: str, base_model: str, hyperparams: dict,
                     metrics: dict, artifact_dir: str) -> tuple[str, str, str]:
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    model_name = f"ModelForge-{job_name}"
    with mlflow.start_run(run_name=job_name) as run:
        mlflow.log_params({"base_model": base_model, **hyperparams})
        mlflow.log_metrics({k: float(v) for k, v in metrics.items()
                            if isinstance(v, (int, float))})
        mlflow.log_artifacts(artifact_dir, artifact_path="model")
        result = mlflow.register_model(
            f"runs:/{run.info.run_id}/model", model_name)
    return run.info.run_id, model_name, result.version
```

```python
# services/train-worker/worker/tasks.py
import json, tempfile
from worker.celery_app import celery_app
from modelforge_common.task_names import TRAIN_TASK
from modelforge_common.enums import JobStatus
from worker.db import build_engine, set_job_status, load_job
from worker.storage import read_snapshot
from worker.recipes import get_recipe
from worker.mlflow_utils import log_and_register

def run_recipe(task_type, df, base_model, hyperparams, output_dir):
    return get_recipe(task_type).train(df=df, base_model=base_model,
                                       hyperparams=hyperparams, output_dir=output_dir)

@celery_app.task(name=TRAIN_TASK, bind=True)
def train_task(self, training_job_id: int):
    engine = build_engine()
    set_job_status(engine, training_job_id, JobStatus.RUNNING)
    try:
        job = load_job(engine, training_job_id)
        hp = job["hyperparams"]
        hp = json.loads(hp) if isinstance(hp, str) else (hp or {})
        df = read_snapshot(job["storage_uri"])
        with tempfile.TemporaryDirectory() as out:
            result = run_recipe(job["task_type"], df, job["base_model"], hp, out)
            run_id, model_name, version = log_and_register(
                job_name=job["name"], base_model=job["base_model"], hyperparams=hp,
                metrics=result.metrics, artifact_dir=result.artifact_dir)
        set_job_status(engine, training_job_id, JobStatus.SUCCEEDED, mlflow_run_id=run_id)
        return {"run_id": run_id, "model_name": model_name, "version": version,
                "metrics": result.metrics}
    except Exception as e:
        set_job_status(engine, training_job_id, JobStatus.FAILED, error=str(e))
        raise
```

> 注:测试通过 monkeypatch 替换 `tasks.build_engine / read_snapshot / run_recipe / log_and_register`,因此这些名字都在 `tasks` 模块顶层 import 进来。

- [ ] **Step 4: 运行确认通过**

Run: `cd services/train-worker && pytest tests/test_train_task.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/train-worker/worker/mlflow_utils.py services/train-worker/worker/tasks.py
git commit -m "feat(train-worker): mlflow logging and full train task orchestration"
```

---

### Task 17: app-server 从 MLflow 同步 ModelVersion

**Files:**
- Create: `services/app-server/app/services/mlflow_sync.py`
- Create: `services/app-server/app/api/models.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_mlflow_sync.py`

- [ ] **Step 1: 写失败测试(mock train_task 结果落库)**

```python
# services/app-server/tests/test_mlflow_sync.py
from app.services.mlflow_sync import upsert_model_version_from_result

def test_upsert_creates_model_version(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.training import TrainingJob
    eng = create_engine(f"sqlite:///{tmp_path}/t.db"); Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False)
    db = S()
    job = TrainingJob(name="j", dataset_version_id=1, base_model="bert-base",
                      task_type="classification", hyperparams={}); db.add(job); db.commit()
    mv = upsert_model_version_from_result(db, job.id, {
        "run_id": "r1", "model_name": "ModelForge-j", "version": "1",
        "metrics": {"accuracy": 0.9}})
    assert mv.mlflow_version == "1"
    assert mv.train_metrics["accuracy"] == 0.9
    assert mv.task_type == "classification"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && pytest tests/test_mlflow_sync.py -q`
Expected: FAIL — `ModuleNotFoundError: app.services.mlflow_sync`

- [ ] **Step 3: 实现同步 + 查询 API**

```python
# services/app-server/app/services/mlflow_sync.py
from sqlalchemy.orm import Session
from app.models.training import TrainingJob, ModelVersion

def upsert_model_version_from_result(db: Session, training_job_id: int,
                                     result: dict) -> ModelVersion:
    job = db.get(TrainingJob, training_job_id)
    if not job:
        raise ValueError("training job not found")
    mv = ModelVersion(
        name=result["model_name"], source_training_job_id=job.id,
        mlflow_model_name=result["model_name"], mlflow_version=str(result["version"]),
        task_type=job.task_type, base_model=job.base_model,
        train_metrics=result.get("metrics", {}),
        artifact_uri=f"models:/{result['model_name']}/{result['version']}")
    db.add(mv); db.commit(); db.refresh(mv)
    return mv
```

```python
# services/app-server/app/api/models.py
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.training import ModelVersion
from pydantic import BaseModel

class ModelVersionOut(BaseModel):
    id: int
    name: str
    mlflow_version: str
    task_type: str
    base_model: str
    train_metrics: dict
    stage: str
    class Config: from_attributes = True

router = APIRouter(prefix="/model-versions", tags=["models"])

@router.get("", response_model=list[ModelVersionOut])
def list_model_versions(db: Session = Depends(get_db)):
    return db.execute(select(ModelVersion).order_by(ModelVersion.id.desc())).scalars().all()
```

```python
# services/app-server/app/main.py  (追加)
from app.api import models
app.include_router(models.router)
```

> **状态回流接线**:本计划用最简方案——worker 完成后由 app-server 提供一个内部回调端点 `POST /internal/training-jobs/{id}/result`(下方 Step 补充),worker 在 `train_task` 成功后调用它写 ModelVersion。生产可改为 Celery result backend 轮询;回调更简单,先用回调。

- [ ] **Step 4: 加内部回调端点 + 接线 worker**

在 `app/api/training.py` 追加:

```python
from app.services.mlflow_sync import upsert_model_version_from_result
from pydantic import BaseModel

class TrainResultIn(BaseModel):
    run_id: str
    model_name: str
    version: str
    metrics: dict = {}

@router.post("/internal/{job_id}/result", status_code=201)
def report_result(job_id: int, body: TrainResultIn, db: Session = Depends(get_db)):
    mv = upsert_model_version_from_result(db, job_id, body.model_dump())
    return {"model_version_id": mv.id}
```

在 train-worker `worker/tasks.py` 成功分支后,用 `requests` 回调(在 pyproject 加 `requests>=2.31`,配置加 `app_server_url`):

```python
# tasks.py 成功后追加(import requests, from worker.config import settings)
requests.post(f"{settings.app_server_url}/training-jobs/internal/{training_job_id}/result",
              json={"run_id": run_id, "model_name": model_name,
                    "version": version, "metrics": {
                        k: float(v) for k, v in result.metrics.items()
                        if isinstance(v, (int, float))}}, timeout=10)
```

`worker/config.py` 增加:`app_server_url: str = "http://localhost:8000"`

- [ ] **Step 5: 运行确认通过**

Run: `cd services/app-server && pytest tests/test_mlflow_sync.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add services/app-server/app/services/mlflow_sync.py services/app-server/app/api/models.py services/app-server/app/api/training.py services/app-server/app/main.py services/train-worker/worker/tasks.py services/train-worker/worker/config.py services/train-worker/pyproject.toml
git commit -m "feat: sync ModelVersion from training result via internal callback"
```

---

### Task 18: 端到端冒烟(手动)+ 前端训练/模型页

**Files:**
- Create: `services/app-server/tests/test_e2e_smoke.md`(手动步骤清单)
- Create: `frontend/src/pages/TrainingPage.tsx`
- Create: `frontend/src/pages/ModelsPage.tsx`
- Modify: `frontend/src/App.tsx`、`frontend/src/api/client.ts`

- [ ] **Step 1: 记录端到端手动验证清单**

```markdown
# E2E 冒烟(需 docker compose 全开 + worker 运行)
1. 启动 worker: cd services/train-worker && celery -A worker.celery_app worker -c 1 -l info
2. 启动 app:    cd services/app-server && uvicorn app.main:app --port 8000
3. 建分类数据集并上传 CSV(text,label,>=8 行两类)
4. POST /training-jobs {dataset_version_id, base_model:"prajjwal1/bert-tiny",
   task_type:"classification", hyperparams:{epochs:1,batch_size:4}}
5. 轮询 GET /training-jobs/{id} 直到 status=succeeded
6. GET /model-versions 应出现一条,train_metrics 含 accuracy
7. MLflow UI(:5000)能看到 run 与 Registered Model
```

- [ ] **Step 2: 执行端到端冒烟**

Run: 按上面清单逐步执行。
Expected: job 最终 `succeeded`;`/model-versions` 返回 1 条;MLflow UI 可见注册模型。

- [ ] **Step 3: 前端训练页 + 模型页**

```ts
// frontend/src/api/client.ts  (追加)
export type TrainingJob = { id: number; name: string; status: string; error: string | null };
export type ModelVersion = { id: number; name: string; mlflow_version: string; task_type: string; train_metrics: Record<string, number>; stage: string };
export const listJobs = () => api.get<TrainingJob[]>("/training-jobs").then(r => r.data);
export const createJob = (b: any) => api.post<TrainingJob>("/training-jobs", b).then(r => r.data);
export const listModelVersions = () => api.get<ModelVersion[]>("/model-versions").then(r => r.data);
```

```tsx
// frontend/src/pages/TrainingPage.tsx
import { useEffect, useState } from "react";
import { listJobs, createJob, TrainingJob } from "../api/client";

export function TrainingPage() {
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [dvId, setDvId] = useState("");
  const reload = () => listJobs().then(setJobs);
  useEffect(() => { reload(); const t = setInterval(reload, 3000); return () => clearInterval(t); }, []);
  return (
    <div>
      <h2>训练任务</h2>
      <input placeholder="dataset_version_id" value={dvId} onChange={e => setDvId(e.target.value)} />
      <button onClick={() => createJob({ name: `job-${Date.now()}`, dataset_version_id: Number(dvId),
        base_model: "prajjwal1/bert-tiny", task_type: "classification",
        hyperparams: { epochs: 1, batch_size: 4 } }).then(reload)}>提交训练</button>
      <ul>{jobs.map(j => <li key={j.id}>#{j.id} {j.name} — <b>{j.status}</b>{j.error ? ` (${j.error})` : ""}</li>)}</ul>
    </div>
  );
}
```

```tsx
// frontend/src/pages/ModelsPage.tsx
import { useEffect, useState } from "react";
import { listModelVersions, ModelVersion } from "../api/client";

export function ModelsPage() {
  const [items, setItems] = useState<ModelVersion[]>([]);
  useEffect(() => { listModelVersions().then(setItems); }, []);
  return (
    <div>
      <h2>模型版本</h2>
      <table><thead><tr><th>名称</th><th>版本</th><th>任务</th><th>指标</th><th>stage</th></tr></thead>
        <tbody>{items.map(m => <tr key={m.id}>
          <td>{m.name}</td><td>{m.mlflow_version}</td><td>{m.task_type}</td>
          <td>{JSON.stringify(m.train_metrics)}</td><td>{m.stage}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
```

```tsx
// frontend/src/App.tsx  (替换为带导航的版本)
import { DatasetsPage } from "./pages/DatasetsPage";
import { DatasetDetailPage } from "./pages/DatasetDetailPage";
import { TrainingPage } from "./pages/TrainingPage";
import { ModelsPage } from "./pages/ModelsPage";

export default function App() {
  const path = window.location.pathname;
  const m = path.match(/^\/datasets\/(\d+)$/);
  let page = <DatasetsPage />;
  if (m) page = <DatasetDetailPage id={Number(m[1])} />;
  else if (path === "/training") page = <TrainingPage />;
  else if (path === "/models") page = <ModelsPage />;
  return (
    <div>
      <nav style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <a href="/">数据集</a><a href="/training">训练</a><a href="/models">模型</a>
      </nav>
      {page}
    </div>
  );
}
```

Run: `cd frontend && npm run build`
Expected: 构建成功;`npm run dev` 后三个页面可访问,训练页 3 秒轮询状态,模型页显示训练产出的版本。

- [ ] **Step 4: 提交**

```bash
git add services/app-server/tests/test_e2e_smoke.md frontend/src
git commit -m "feat(frontend): training and models pages; e2e smoke checklist"
```

---

## 自查(Self-Review)

**Spec 覆盖度:**
- 训练集管理 + 版本管理 → Task 7–11 ✅
- 评估集管理 → Dataset(kind=eval) 复用同一套 CRUD(Task 9 校验已含 eval 任务列)✅(评估*流程*在后续计划)
- 模型版本管理 → Task 12/17(MLflow Registry + 镜像表)✅
- classification 训练全链路 → Task 12–18 ✅
- 三服务骨架 + 基础设施 → Task 1–6 ✅
- 后续计划(本计划范围外,已在 spec 第 10 节标注):评估流程执行、ner/pair/embedding recipe、在线部署 model-server。

**占位符扫描:** 无 TBD/TODO;每个代码步骤含完整代码。

**类型一致性:** `TrainResult(metrics, artifact_dir, label_names)` 在 Task 15 定义,Task 16 使用一致;`send_train_task` 在 celery_client 定义、service 引用、test monkeypatch 路径一致;train_task 结果字段 `{run_id, model_name, version, metrics}` 在 Task 16 产出、Task 17 回调消费一致。

**已知前置依赖:** Task 15 的 slow 测试与 Task 18 端到端需联网下载 `prajjwal1/bert-tiny` 与运行中的基础设施;CI 中可用 `-m "not slow"` 跳过重训练测试。
