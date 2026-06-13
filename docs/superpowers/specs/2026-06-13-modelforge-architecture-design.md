# ModelForge 架构设计文档

- 日期:2026-06-13
- 状态:已评审,待实现计划
- 范围:平台整体架构(三服务 + 前端 + 数据/版本/评估/模型管理)

## 1. 背景与目标

ModelForge 是一个**小团队内部**使用的 NLP 模型训练与服务平台,围绕 BERT 架构类编码器模型(**不做大模型微调,不做图像**)。需支持的能力:

- 训练集管理 + 版本管理
- 评估集管理
- 评估流程
- 模型版本管理
- 在线推理部署

### 支持的任务类型(task_type)

| task_type | 说明 | 训练方式 | 评估指标 |
|---|---|---|---|
| `classification` | 单/多标签文本分类、意图、情感 | HF `Trainer` (SequenceClassification) | accuracy / precision / recall / F1 |
| `ner` | 序列标注 / 实体识别 | HF `Trainer` (TokenClassification) | entity-level F1 (seqeval) |
| `pair` | 句对 / 语义相似度 | HF `Trainer` / CoSENT | Spearman / Pearson |
| `embedding` | 检索向量模型微调(BGE / m3e / gte) | sentence-transformers / FlagEmbedding,对比学习 | recall@k / MRR / nDCG(MTEB 式检索) |

> **关键约束**:`embedding` 与其余三类训练范式不同(对比学习 + 难负样本挖掘 + 检索式评估)。架构必须把 `task_type` 作为一等公民,由 train-worker 按 recipe 分流。

### 非目标(YAGNI)

- 不做大语言模型 SFT/LoRA、不做图像分类(后续可扩展,接口预留)
- 不上 Kubernetes(单机/几台 GPU)
- 不做复杂多租户 / 配额(小团队,基础 RBAC 即可)
- 数据集版本不做 diff / 增量(<百万行,全量快照足够)

## 2. 关键架构决策

### 决策 1:任务编排骨架 = Celery + Redis
app-server 投递任务到 Redis,train-worker 作为 Celery worker 消费。GPU 并发由 worker concurrency 控制。理由:成熟、重试/超时/可观测现成,小团队部署成本低;单机/几台 GPU 场景不需要 K8s。

### 决策 2:评估在 worker 内进程批量推理
评估任务也投递给 train-worker,直接 load 模型权重做 batch 推理算指标。理由:快、准、无网络开销,模型只 load 一次,复用 GPU 调度。**model-server 专注在线部署**,不参与评估。职责清晰:worker = 离线批处理(训练 + 评估),model-server = 在线服务。

### 决策 3:模型版本复用 MLflow Model Registry
版本号、stage 流转(none/staging/prod)、产物存储交给 MLflow。业务侧 `ModelVersion` 表只镜像关键字段(供查询和评估关联),不自建权重存储。

### 决策 4:数据集版本 = 不可变全量快照
每次"提交"数据集生成新 `DatasetVersion`,全量写 parquet/jsonl 到 MinIO + checksum。保证训练可复现。<百万行,无需增量。

### 决策 5:难负样本挖掘做成可配置步骤
`embedding` 训练时,hard-negative mining 作为训练前可选步骤:
- `negatives.mode = auto`:用基线模型检索 top-k 自动挖掘难负样本
- `negatives.mode = provided`:使用数据集自带的 `neg` 字段
默认 `auto`(无 neg 时回退随机采样)。

## 3. 整体架构

```
┌─────────────┐     HTTP/JSON      ┌──────────────────────────────┐
│  React 前端  │ ◄────────────────► │  app-server (FastAPI)        │
│  Vite + TS  │                    │  业务/API/认证/编排            │
└─────────────┘                    └──────────────────────────────┘
                                      │            │           │
                          ┌───────────┘            │           └──────────┐
                          ▼                        ▼                      ▼
                   ┌────────────┐          ┌──────────────┐       ┌──────────────┐
                   │ PostgreSQL │          │ Redis(队列)  │       │ MinIO / S3   │
                   │ 业务元数据  │          │ Celery broker│       │ 数据集快照     │
                   └────────────┘          └──────────────┘       │ + MLflow产物  │
                          ▲                        │              └──────────────┘
                          │                        ▼                      ▲
                          │              ┌──────────────────────┐         │
                          │              │ train-worker (Celery) │────────┘
                          │              │ GPU机器 · 训练+评估    │
                          │              │ HF Trainer / ST·Flag  │
                          │              └──────────┬────────────┘
                          │                         │ log metrics / register model
                          │                         ▼
                          │              ┌──────────────────────┐
                          └──────────────│ MLflow Tracking+Registry│
                                         └──────────┬────────────┘
                                                    │ load registered model
                                                    ▼
                                         ┌──────────────────────┐
                          调用方 ◄────────│ model-server (FastAPI)│
                                         │ 在线推理 /predict /embed│
                                         └──────────────────────┘
```

### 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React + TypeScript + Vite;组件库 Ant Design(数据后台)或 shadcn/ui;TanStack Query 数据请求 |
| app-server | FastAPI + SQLAlchemy + Alembic + Pydantic;Celery 客户端 |
| train-worker | Celery worker + HuggingFace Transformers/Trainer + sentence-transformers + FlagEmbedding + datasets;MLflow client |
| model-server | FastAPI + transformers/sentence-transformers 运行时;启动从 MLflow Registry 拉权重 |
| 基础设施 | PostgreSQL、Redis、MinIO(S3 兼容)、MLflow(后端共用同一 PG + MinIO artifact store) |

## 4. 服务边界(单一职责)

| 服务 | 职责 | 不负责 |
|---|---|---|
| **app-server** | 认证、CRUD、版本管理、任务编排、对前端 API | 不跑训练/推理 |
| **train-worker** | 离线批处理:训练 + 评估(GPU) | 不对外提供 HTTP |
| **model-server** | 在线推理服务 | 不做训练/评估 |
| **MLflow** | 实验跟踪 + 模型注册表 + 产物存储 | 不存业务关系数据 |

## 5. 数据模型(PostgreSQL 核心表)

```
User                — 轻量(id, name, email, role)

Dataset             — 数据集(训练集/评估集统一管理)
  id, name, kind(train|eval), task_type, schema(jsonb), created_by

DatasetVersion      — 不可变快照(版本管理核心)
  id, dataset_id, version_no, storage_uri(MinIO parquet/jsonl),
  row_count, checksum, stats(jsonb), note, created_at

TrainingJob         — 训练任务
  id, name, dataset_version_id, base_model, task_type,
  hyperparams(jsonb), status, celery_task_id, mlflow_run_id,
  error, created_by, timestamps

ModelVersion        — 模型版本(镜像 MLflow Registry)
  id, name, source_training_job_id, mlflow_model_name, mlflow_version,
  task_type, base_model, train_metrics(jsonb),
  stage(none|staging|prod), artifact_uri

EvalRun             — 评估流程
  id, model_version_id, dataset_version_id(eval 集版本),
  metric_config(jsonb), status, celery_task_id, results(jsonb),
  per_sample_uri(明细存 MinIO), created_by, timestamps

Deployment          — 在线部署
  id, model_version_id, endpoint, mode(online),
  status(running|stopped), replicas, config(jsonb), timestamps
```

- **EvalSet** 复用 `Dataset(kind=eval)`,不单独建表。
- 数据集版本(app-server 自建全量快照)与模型版本(MLflow Registry)两条线,职责分离。

### 数据集 schema 约定(按 task_type)

| task_type | 存储 schema(parquet/jsonl 列) |
|---|---|
| classification | `text`, `label`(多标签为 `labels: []`) |
| ner | `tokens: []`, `tags: []`(BIO) |
| pair | `text_a`, `text_b`, `label`/`score` |
| embedding | `query`, `pos: []`, `neg: []`(neg 可选) |

## 6. 关键工作流

### 6.1 训练流程
1. 前端选 数据集版本 + base_model + task_type + 超参 → app-server 建 `TrainingJob`,投 Celery 任务。
2. train-worker 消费:从 MinIO 拉数据集快照 → 按 `task_type` 分流 recipe:
   - classification/ner/pair → HF `Trainer`
   - embedding → (可选)难负挖掘 → sentence-transformers/FlagEmbedding 对比学习
3. 训练中 metrics/params 实时写 MLflow;完成后权重注册到 MLflow Registry。
4. app-server 监听完成(回调 / 状态轮询),写 `ModelVersion`,状态回流。

### 6.2 评估流程(worker 批量推理)
1. 前端选 模型版本 + 评估集版本 + 指标配置 → 建 `EvalRun`,投 Celery。
2. worker load 模型权重 → 对评估集 batch 推理 → 按 task_type 算指标:
   - classification: accuracy/precision/recall/F1
   - ner: entity-level F1
   - pair: Spearman/Pearson
   - embedding: recall@k / MRR / nDCG
3. 汇总指标写 `EvalRun.results`,明细落 MinIO。
4. 同一评估集上多个模型版本横向对比(Leaderboard 视图)。

### 6.3 部署流程(model-server 在线服务)
1. 前端对某 `ModelVersion` 点"部署" → app-server 建 `Deployment`,通知 model-server。
2. model-server 从 MLflow Registry 拉权重加载,暴露:
   - `/predict`(分类 / NER)
   - `/embed`(向量)
   - `/similarity`(句对)
3. 支持停止 / 切换版本(灰度后续扩展)。

## 7. 任务状态机

`TrainingJob` / `EvalRun` 状态:`pending → running → succeeded | failed | cancelled`
`Deployment` 状态:`pending → running → stopped | failed`

状态由 Celery worker 更新回 PG;app-server 提供查询与轮询接口给前端。

## 8. 错误处理

- Celery 任务失败重试 + 超时;最终失败写 `error` 字段,状态置 `failed`。
- 数据集快照 checksum 校验,训练前校验 schema 与 task_type 匹配。
- model-server 加载失败回滚 `Deployment` 状态并告警。
- MLflow / MinIO 不可用时,app-server 返回明确错误,不静默吞掉。

## 9. 测试策略

- app-server:pytest + 测试 PG(testcontainers / sqlite 兜底),覆盖 CRUD、版本快照、任务投递。
- train-worker:每类 task_type 的 recipe 用极小数据集跑通(冒烟训练),指标计算单测。
- model-server:加载 + 推理端点契约测试。
- 端到端:小数据集走 训练 → 注册 → 评估 → 部署 → 推理 全链路冒烟。

## 10. 分阶段实现建议(供后续拆 plan)

1. **基础设施 + 骨架**:PG schema/Alembic、Docker Compose(PG/Redis/MinIO/MLflow)、三服务空壳。
2. **数据集与版本管理**:Dataset/DatasetVersion CRUD + 快照落 MinIO + 前端页面。
3. **训练流程(先 classification)**:TrainingJob + Celery + HF Trainer recipe + MLflow 记录 + ModelVersion。
4. **评估流程**:EvalRun + worker 批量推理 + 指标 + Leaderboard。
5. **扩展 task_type**:ner → pair → embedding(含难负挖掘)。
6. **在线部署**:model-server + Deployment 管理。

## 11. 待确认/默认决策记录

以下三点在评审中采用推荐默认值(可在实现前调整):
1. 模型注册表用 MLflow(非自建)—— 采用。
2. 数据集全量快照版本(非 diff)—— 采用。
3. 难负样本挖掘做成可配置步骤(默认 auto)—— 采用。
