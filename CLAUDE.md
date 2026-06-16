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
- **ml-worker(macOS)启动**(原 train-worker,现还跑评估 / Prompt 评测 / badcase 打分):必须 `--pool=solo` + 环境变量 `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`,否则 Celery prefork 在 fork 后初始化 PyTorch Metal(MPS)会 `SIGABRT`。worker 跑在 `services/ml-worker/.venv`(`uv venv --system-site-packages` 复用 base 重依赖)。hard-kill(`kill -9`)worker 会把已 prefetch 的任务卡在 redis `unacked`(~1h 不重投),换 worker 优先优雅停止。
- **自动命名**:训练任务名 / 模型名 = 本地时间戳 `yyyyMMddHHmmss`(前端 `tsName()` 生成,worker `model_name = job_name`)。
- **model-server API 信封**:所有响应统一 `{code, data, message}`(`code=0` 成功,非 0 = HTTP 状态码;`data` 出错为 null)。**HTTP 状态码保留**,app-server 调 `/load` 仍靠 `raise_for_status()`。改 model-server 端点时保持信封。
- 改 RBAC 权限目录时,`app/bootstrap.py` 的 `PERMISSION_CATALOG`/`SYSTEM_ROLES` 与对应编号迁移(如 `006_model_write_perm.sql`、`014_badcase_perms.sql`、`018_llm_manage_perm.sql`、`020_prompt_perms.sql`、`022_prompteval_perms.sql`、`024_prompteval_annotate_perm.sql`)两处一起改。当前 = **22 表 / 22 权限**(`test_migrations_apply` 的 `ntab`/`nperm` 与 `test_bootstrap` 权限计数会一起断言,改 schema/权限时同步)。角色管理页动态列出库里全部权限,**加了权限迁移记得重启 app-server**(启动才自动应用),否则新建角色看不到。

## Badcase 闭环修复

- **上报鉴权走 `X-Api-Key`**,不是 JWT:`POST /badcase/report` 用 `app.api_key_auth.require_api_key("badcase:report")`,坏例的 `source` = API Key 名称;`(source, source_ref)` 幂等去重。其余 `/badcases/**` 管理端点仍走 JWT + 权限码(`badcase:read` / `badcase:annotate`)。
- **API Key 明文落库**(`016_api_key_plaintext.sql`),以支持前端随时复制;签发/吊销需 `apikey:manage`。
- **badcase 评分是 best-effort**:再训练时 worker(`worker/tasks.py`)对该任务关联的已标注坏例打分,把已修复的写回 `badcase_fixes` 回调 app-server,并把 `badcase_fix_rate` 写进 metrics + MLflow。**评分任何异常都不能让一次成功的训练失败**(已用 try/except 包住)。
- **`fixed_by` 是 JSON 列**(`015_badcase_fixed_by.sql`),元素 `{model_version_id, version_label, at}`。`badcase_service.mark_fixed` 追加去重后**整体重新赋值**该列以触发 SQLAlchemy 脏标记;`summary()` 按 `version_label` 聚合出每个版本的修复条数(前端展示「V5 修复 N 条」)。
- `summary()` 刻意只 `select` 聚合所需列 + LEFT JOIN `ModelVersion`,**避免**水合整行 Badcase ORM(大 JSON)与级联 selectin,否则慢。改动时保持这个写法。

## 大模型 Prompt 评测(子项目 A–E)

> 用平台调用**外部 LLM API**(OpenAI 协议)做 Prompt 盲测人工评估 + AI 自动评估。**不微调大模型**。

- **LLM 设置(A)**:`llm_providers`(一条 = 一个供应商,下挂多个 `llm_models`),`api_key` **明文落库、`masked_key` 掩码读**(`017`);`llm:manage`。连通性测试 + Prompt 评测都走共享的 `modelforge_common/llm_client.py` 的 `chat(base_url, api_key, model_id, messages)`(OpenAI `/chat/completions`)。
- **Prompt 管理(B)**:`prompts` + `prompt_versions`(**不可变版本**),`{{ 参数 }}` 双花括号;解析/校验/渲染统一用 `modelforge_common/prompt_template.py`(`extract_params`/`validate_template`/`render`,支持中文参数名)。`prompt:read`/`prompt:write`。**Prompt 测试集复用 `datasets`**:`kind="prompt"`、`task_type="prompt"`(列即参数);prompt 类数据集**没有固定 task_type**,序列化/下载传 `None`(`TaskType("prompt")` 会抛),模板下载对 prompt kind 返回 400。
- **评测引擎(C1)**:`prompt_eval_runs/arms/items/outputs`;三种 `eval_type` = `multi_prompt`(多 Prompt 盲测)/`multi_model`(多模型盲测)/`single_prompt`(单 Prompt 版本对比);worker task `modelforge.prompt_eval`(`worker/prompt_eval.py`),逐 item 渲染→调 LLM→写 outputs;`NaN` 单元格要 `_clean` 成 `None`(否则 `json.dumps` 出字面 `NaN`,PG JSON 插入失败)。`prompteval:read`/`prompteval:run`。
- **盲测(C2,关键)**:`GET /prompt-evals/{id}/items` 用 `random.Random(run_id)` 把「臂 → A/B/C」**在整轮内固定随机一次**(随机分配、不按版本号、**界面隐藏版本**);所以「每条都选 A」= 始终选同一个臂。verdict 存**真实 `arm_id`**(前端持有不显示)。版本只在**统计页揭晓**。**改动保持「per-run 固定 + 不揭晓」**——别改回 per-item 打乱(会让「总选 A」散到不同臂,用户误解),也别在评估界面显示版本。`prompteval:annotate`。
- **AI 自动评估(D)**:AI 判定写入 `prompt_eval_items` 的**并行 `ai_*` 列**(`023` 人工 verdict 列、`025` AI 列),与人工 verdict **并存、互不覆盖**。worker task `modelforge.prompt_ai_eval`,评判模型用 A 中启用的 `llm_model`;**强制 JSON** 输出,worker 正则抽第一个 `{...}` 宽容解析;**单条失败隔离**(LLMError/非 JSON/越界 → 判定列留空但仍写 `ai_reasoning` + `ai_evaluated_at` 防重评,继续下一条)。评判系统指令存 `app_settings`(`025` 通用键值表)键 `ai_eval_prompt`,默认值是代码常量 `DEFAULT_AI_EVAL_PROMPT`(**不入种子**,GET 返回库值或默认);读写 `llm:manage`(`/settings/ai-eval-prompt`)。
- **统计(实时,两套指标)**:`app/services/prompt_eval_stats.py` 的 `stats()` 返回 `{eval_type, total, human:{...}, ai:{...}}` —— **人工 + AI 各一套**(多臂:各臂胜率/最优 `best_arm_id`/`all_bad`;单 prompt:好率 + 对上一版本的变好/变坏 `comparison`,**对比仅基于人工** `is_good`,找 `compare_to_version_id` 最近一次已评 `single_prompt` run 按 `(dataset_version_id, row_index)` 匹配)。盲测工作台标完最后一条右侧自动切「统计」视图。
- **统计页/首页聚合(E)**:`/stats`(prompts、prompt_eval_runs、prompt_eval_items、人工/AI 已评数)与 `/stats/charts`(`prompt_eval_runs_by_type`)按 `prompt:read`/`prompteval:read` **门控**;item 计数 join `PromptEvalRun` 后 `apply_scope`(item 无 `created_by`,按其 run 归属做数据范围)。

## 前端约定

- **每页条数**统一引用 `frontend/src/constants.ts` 的 `DEFAULT_PAGE_SIZE`(生产=20);各列表用服务端分页(`paginate`/`X-Total-Count`)。
- **任务类型标签与下拉分组**统一用 `frontend/src/taskGroups.ts` 的 `TASK_LABEL` 与 `groupByTask()`(按 classification→ner→pair→embedding 排组,组内名称升序、版本号降序)。新增「模型版本 / 数据集版本」下拉时复用它做 `<optgroup>` 分组,别再各页自己拼平铺列表。
- **「Prompt 评测」并入「测试」模块**:`components/TestModule.tsx` 是带 Tab 的壳,路由 `/eval`(模型测试 = `EvalPage`)、`/eval/prompt`(Prompt 评测 = `PromptEvalsPage`)、`/eval/prompt/:id/evaluate`(盲测工作台 = `PromptEvalWorkbench`,全屏不带 Tab)。Tab 按权限显示(`eval:read` / `prompteval:read`)。`AppShell` 的「测试」导航项用 `perms: ["eval:read","prompteval:read"]`(any-of)显示;**「Prompt」管理(`/prompts`)是独立导航项**,不要并进测试。首页「Prompt 评测」卡片跳 `/eval/prompt`。
