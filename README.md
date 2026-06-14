# ModelForge

小团队内部使用的 **NLP 模型训练与服务平台**,围绕 BERT 架构类编码器模型(**不做大模型微调,不做图像**)。提供训练集/评估集管理与版本管理、训练流程、评估流程、模型版本管理,以及在线推理部署。

![ModelForge 架构总览](images/architecture.png)

## 功能

- **数据集管理 + 版本管理**:训练集 / 评估集统一管理,每次提交生成不可变全量快照(parquet)落对象存储,带 checksum,保证训练可复现。
- **训练流程**:按 `task_type` 分流 recipe(分类已落地;NER / 句对 / embedding 微调规划中),实验与产物记录到 MLflow。
- **评估流程**:对某模型版本 + 评估集版本发起评估,worker 加载已注册模型批量推理算指标,结果回写 `EvalRun`,可在同一评估集上横向对比多个模型版本(分类已落地)。
- **模型版本管理**:复用 MLflow Model Registry,业务侧 `ModelVersion` 表镜像关键字段供查询与评估关联。
- **在线部署**:一键把模型版本部署到 model-server,从 Registry 拉权重加载,按 task_type 暴露 `/predict`(分类/NER)、`/embed`(向量)、`/similarity`(句对);app-server 提供部署管理(创建/列表/停止)。
- **认证与 RBAC**:JWT 登录 + 自定义角色(固定权限目录上自由组合)+ 角色级数据范围(`all`/`own`,`own` 仅见/改自己 `created_by` 的资源);超管管理用户(角色/启停/改密)与角色(权限集/数据范围);内部回调用 `X-Internal-Token` 护栏。

支持的任务类型:

| task_type | 说明 | 训练方式 | 评估指标 |
|---|---|---|---|
| `classification` | 单/多标签文本分类、意图、情感 | HF `Trainer` | accuracy / precision / recall / F1 |
| `ner` | 序列标注 / 实体识别 | HF `Trainer` | entity-level F1 |
| `pair` | 句对 / 语义相似度 | HF `Trainer` / CoSENT | Spearman / Pearson |
| `embedding` | 检索向量模型微调(BGE / m3e / gte) | sentence-transformers / FlagEmbedding | recall@k / MRR / nDCG |

> 四类 task_type 的训练 recipe 与评估器均已落地;在线部署见路线图。

## 架构

四个组件 + 基础设施,职责单一、边界清晰:

| 组件 | 技术栈 | 职责 | 不负责 |
|---|---|---|---|
| **app-server** | FastAPI + SQLAlchemy + 编号 SQL 迁移 | 认证、CRUD、版本管理、任务编排、对前端 API | 不跑训练/推理 |
| **train-worker** | Celery + HuggingFace + sentence-transformers | 离线批处理:训练 + 评估(GPU) | 不对外提供 HTTP |
| **model-server** | FastAPI + transformers | 在线推理服务 | 不做训练/评估 |
| **前端** | React + TypeScript + Vite | 数据集 / 训练 / 模型版本页面 | — |
| 基础设施 | PostgreSQL / Redis / MinIO / MLflow | 元数据 / 队列 / 对象存储 / 实验与注册表 | — |

**服务解耦**:app-server 与 train-worker 互不 import 代码,仅通过 PostgreSQL + 共享的 Celery 任务名(`services/common`)耦合;app-server 用 `send_task(name)` 投递,worker 完成后写 PG 状态并 HTTP 回调 app-server 创建 `ModelVersion`。

详见架构设计文档:[`docs/superpowers/specs/2026-06-13-modelforge-architecture-design.md`](docs/superpowers/specs/2026-06-13-modelforge-architecture-design.md)。

## 目录结构

```
ModelForge/
├── docker-compose.yml            # PG / Redis / MinIO / MLflow
├── .env.example                  # 环境变量示例
├── images/architecture.png       # 架构图
├── services/
│   ├── common/                   # 共享枚举(TaskType/JobStatus/DatasetKind)+ 任务名常量
│   ├── app-server/               # FastAPI 业务服务 + db/migrations/ 编号 SQL 迁移
│   ├── train-worker/             # Celery worker + 训练 recipe
│   └── model-server/             # 在线推理服务(健康检查骨架)
├── frontend/                     # React + TS + Vite
└── docs/superpowers/             # 架构 spec 与实现计划
```

## 关键工作流

**训练**:前端选 数据集版本 + base_model + 超参 → app-server 建 `TrainingJob` 并投 Celery → worker 拉快照、按 `task_type` 跑 recipe、metrics/产物写 MLflow 并 `register_model` → 回写状态 + 回调创建 `ModelVersion`。

**数据集版本**:上传 CSV/JSONL → 按 task_type 校验 schema → 全量快照写 MinIO(parquet + sha256)→ `DatasetVersion` 自增版本号入库。

## 快速开始

### 1. 启动基础设施

```bash
cp .env.example .env
docker compose up -d                      # PG / Redis / MinIO / MLflow
# 首次创建 MinIO bucket
docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker compose exec minio mc mb -p local/datasets local/mlflow
```

### 2. 安装依赖(建议用一个虚拟环境)

```bash
pip install -e services/common              # 先装共享包(非 PyPI)
pip install -e 'services/app-server[dev]'
pip install -e 'services/train-worker[dev]' # 含 torch/transformers,首次较慢
pip install -e 'services/model-server[dev]'
```

### 3. 初始化数据库

迁移在 app 启动时自动应用;也可手动:

```bash
cd services/app-server && python -m app.migrate   # 应用 db/migrations/ 下未执行的编号 SQL
```

> `001_init_schema.sql` 建表、`002_seed_rbac.sql` 写种子(权限/角色/初始超管)。初始超管 `admin@modelforge.local` / `admin12345`(**首登后请改**)。生产环境务必用 env 覆盖 `JWT_SECRET`、`INTERNAL_TOKEN`、MinIO 凭证等默认值。**所有业务端点都需登录**。

### 4. 启动服务

```bash
# app-server
cd services/app-server && uvicorn app.main:app --port 8000 &

# train-worker(默认 MinIO 凭证开箱即用)
cd services/train-worker && celery -A worker.celery_app worker -c 1 -l info &

# 前端
cd frontend && npm install && npm run dev
```

> **关于 MLflow 访问 MinIO 的凭证**:MLflow 上传模型产物到 MinIO 的 `mlflow` 桶时,走的是 AWS SDK 标准变量(`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `MLFLOW_S3_ENDPOINT_URL`),与平台自有的 `S3_ACCESS_KEY`/`S3_SECRET_KEY`(访问 `datasets` 桶)是两套通道。worker 已在 `worker/mlflow_utils.py` 里**从自身配置显式设置**这些变量,因此无需手动 export;改用自定义凭证时,设置 worker 的 `S3_ACCESS_KEY`/`S3_SECRET_KEY`/`S3_ENDPOINT_URL`(环境变量或 `.env`)即可。

## 端到端冒烟

参见 [`services/app-server/tests/test_e2e_smoke.md`](services/app-server/tests/test_e2e_smoke.md):建分类数据集 → 上传 CSV → 提交训练 → 轮询至 `succeeded` → `/model-versions` 出现新版本 → MLflow UI(`:5000`)可见 run 与注册模型。

## 测试

```bash
cd services/common       && pytest -q
cd services/app-server   && pytest -q
cd services/train-worker && pytest -q -m "not slow"   # 跳过真实训练
cd services/train-worker && pytest -q -m slow         # 真实训练 bert-tiny(需联网,~30s)
cd services/model-server && pytest -q
```

## 主要 API

> 除 `POST /auth/login` 外,所有端点需带 `Authorization: Bearer <token>`;按角色权限码鉴权,按角色数据范围过滤。

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/auth/login` | 登录,返回 JWT + 用户权限 |
| `GET` | `/auth/me` | 当前用户信息与权限码 |
| `GET/POST/PATCH` | `/users`、`/users/{id}` | 用户管理(需 `user:manage`) |
| `GET/POST/PATCH/DELETE` | `/roles`、`/permissions` | 角色与权限目录(需 `role:manage`) |
| `POST` | `/datasets` | 创建数据集 |
| `GET` | `/datasets` | 数据集列表 |
| `POST` | `/datasets/{id}/versions` | 上传 CSV/JSONL 生成新版本 |
| `GET` | `/datasets/{id}/versions` | 版本列表 |
| `POST` | `/training-jobs` | 提交训练任务 |
| `GET` | `/training-jobs/{id}` | 查询任务状态 |
| `GET` | `/model-versions` | 模型版本列表 |
| `POST` | `/eval-runs` | 发起评估(模型版本 + 评估集版本) |
| `GET` | `/eval-runs?dataset_version_id=` | 评估列表(可按评估集版本过滤做 Leaderboard) |
| `GET` | `/eval-runs/{id}` | 查询评估状态与指标 |
| `POST` | `/deployments` | 部署某模型版本(通知 model-server 加载) |
| `GET` | `/deployments` | 部署列表 |
| `POST` | `/deployments/{id}/stop` | 停止部署 |

model-server(默认 `:8001`)推理端点:`POST /load`、`POST /predict`、`POST /embed`、`POST /similarity`、`GET /loaded`、`DELETE /loaded/{model_version_id}`。

## 路线图

已完成:

- **基础地基(phases 1–3)**:基础设施 + 三服务骨架、数据集与版本管理、classification 训练全链路(训练 → MLflow 注册 → 模型版本)。
- **评估流程(phase 4)**:发起评估 → worker 加载已注册模型批量推理 → 指标回写 `EvalRun` → 同一评估集横向对比。
- **全部 task_type recipe(phase 5)**:`classification` / `ner` / `pair` / `embedding`(含难负样本挖掘)训练 recipe 与对应评估器,接入 worker 的 `get_recipe`/`get_evaluator` 分流。
- **在线部署(phase 6)**:`Deployment` 管理 + model-server 内存模型库,从 MLflow Registry 拉权重,按 task_type 暴露 `/predict` `/embed` `/similarity`。

后续可做(均超出当前范围):per-sample 评估明细落盘、部署灰度/多副本、更细的 RBAC/配额、大数据集增量版本。

详见实现计划:[基础地基](docs/superpowers/plans/2026-06-13-modelforge-foundation.md)、[评估流程](docs/superpowers/plans/2026-06-13-modelforge-evaluation.md)、[recipes](docs/superpowers/plans/2026-06-13-modelforge-recipes.md)、[在线部署](docs/superpowers/plans/2026-06-13-modelforge-deployment.md)。
