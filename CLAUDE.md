# ModelForge — 项目约定

## 数据库 schema 与编号 SQL 迁移

- 权威 schema 来源 = `services/app-server` 的 SQLAlchemy 模型(`app/models/`),供 app 查询使用。
- 数据库变更通过 **`services/app-server/db/migrations/` 下的编号 SQL 文件**(`001_*.sql`、`002_*.sql`…)落库,由 `app/migrate.py` 的 runner 按编号顺序应用,`schema_migrations` 表记录已执行的文件。
- runner 在 **app 启动时(连 PostgreSQL 且 `run_migrations_on_startup=True`)自动应用**未执行的迁移;也可手动 `cd services/app-server && python -m app.migrate`。

### 铁律:改 schema 必须配一个编号 SQL 迁移

**任何改动数据库结构(改 `app/models/**`:加表/列/约束),必须在同一次提交里在 `services/app-server/db/migrations/` 新增一个【下一个编号】的 `.sql` 文件**,写对应的 `CREATE`/`ALTER`,并用幂等写法:
- `CREATE TABLE IF NOT EXISTS ...`
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...`
- 数据用 `INSERT ... ON CONFLICT ... DO NOTHING`

判断标准:`git diff` 动了 `app/models/**`,就必须同时包含一个新的 `db/migrations/NNN_*.sql`。**不要再用 Alembic。** 迁移只前进、不写 down;需要回退就再加一个补偿迁移。

### 种子数据

- 生产种子(权限目录/系统角色/初始超管)= `db/migrations/002_seed_rbac.sql`,随迁移自动应用。
- `app/bootstrap.py` 仅作**测试用程序化 seed**(SQLite 上 `bootstrap.seed(db)`);它与 `002_seed_rbac.sql` 的权限目录/角色必须保持一致。改种子时两处一起改。

### 注意

- MLflow 有**独立的 sqlite backend store**(在 Docker 容器 `modelforge-mlflow` 的卷 `/mlflow/mlflow.db`),与 app 的 PostgreSQL 是两个库;编号 SQL 只含本项目的表,不碰 MLflow。
- 测试用 SQLite + `Base.metadata.create_all`,不跑编号 SQL(PG 方言);`conftest.py` 已把 `run_migrations_on_startup` 关掉。

## 运行与环境约定

- **MLflow = 3.x**(server 与三端客户端都对齐 `>=3.0`)。server 是 Docker 容器 `modelforge-mlflow`(镜像 `ghcr.io/mlflow/mlflow:v3.13.0`),`:5500`,sqlite backend + MinIO `s3://mlflow/` artifacts + `--no-serve-artifacts`(客户端直传 MinIO)。升级镜像前先 `mlflow db upgrade <backend-uri>` 迁移表。
- **MLflow 3.x 注册模型**:`log_artifacts(dir,"model")` + `register_model("runs:/…")` 在 3.x 已失效;改用 `MlflowClient.create_model_version(name, source="runs:/<run>/model", run_id=…)`(产物仍在 artifact 根,predictor 直接 `from_pretrained` 加载)。见 `worker/tasks.py:_register_run_model`。
- **train-worker(macOS)启动**:必须 `--pool=solo` + 环境变量 `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`,否则 Celery prefork 在 fork 后初始化 PyTorch Metal(MPS)会 `SIGABRT`。worker 跑在 `services/train-worker/.venv`(`uv venv --system-site-packages` 复用 base 重依赖)。hard-kill(`kill -9`)worker 会把已 prefetch 的任务卡在 redis `unacked`(~1h 不重投),换 worker 优先优雅停止。
- **自动命名**:训练任务名 / 模型名 = 本地时间戳 `yyyyMMddHHmmss`(前端 `tsName()` 生成,worker `model_name = job_name`)。
- **model-server API 信封**:所有响应统一 `{code, data, message}`(`code=0` 成功,非 0 = HTTP 状态码;`data` 出错为 null)。**HTTP 状态码保留**,app-server 调 `/load` 仍靠 `raise_for_status()`。改 model-server 端点时保持信封。
- 改 RBAC 权限目录时,`app/bootstrap.py` 的 `PERMISSION_CATALOG`/`SYSTEM_ROLES` 与对应编号迁移(如 `006_model_write_perm.sql`)两处一起改。
