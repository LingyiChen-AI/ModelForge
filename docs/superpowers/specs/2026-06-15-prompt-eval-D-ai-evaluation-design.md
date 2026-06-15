# 子项目 D:AI 自动评估 — 设计

> 「大模型 Prompt 评测功能」(PRD:[`PRD/prompt-eval.md`](../../../PRD/prompt-eval.md))第四个子项目。
>
> 整体:A. LLM 设置页(完成)→ B. Prompt 管理 + 测试集(完成)→ C. 评测(C1 引擎 + C2 工作台/统计,完成)→ **D. AI 自动评估**(本文)→ E. 统计页。
>
> 接 C1/C2 的 `prompt_eval_runs/arms/items/outputs` + verdict 列(见 [C1](2026-06-15-prompt-eval-C1-eval-engine-design.md) / [C2](2026-06-15-prompt-eval-C2-workbench-and-stats-design.md))与 A 的 `llm_providers/llm_models`。

## 目标

用一个大模型(评判模型)对某评测的 item 自动判优(多臂选最佳输出、单 prompt 判好坏),把 AI 判定**与人工 verdict 并存**地写回 item,并展示 AI/人工来源与 AI 的原始推理。评判用的系统指令可在设置页配置。

## 范围

**做**:item 的并行 AI verdict 列;通用 `app_settings` 表 + AI 评判系统指令的读写;AI 评估触发 API + worker 评判任务(调 LLM、强制 JSON 解析);设置页的 AI Prompt 编辑;评测列表/工作台的 AI 评估触发与结果展示。

**不做**:人工 vs AI 一致率/对比看板(留 E);AI 评估的进度条/独立状态(以 item AI 列出现作为反馈)。

## 关键决策(已与用户确认)

1. **并存**:AI 判定写入**独立的 AI 列**,不覆盖 C2 的人工 verdict;两者并存、都展示。
2. **设置存储**:新建通用 `app_settings(key, value)` 键值表;本期键 `ai_eval_prompt`(评判系统指令),**默认值是代码常量**,GET 返回「库值或默认」,无需种子。
3. **执行**:worker 异步(像 C1),顺序逐条调评判模型。
4. **输出契约**:**强制 JSON**——多臂 `{"winner": 序号}` 或 `{"all_bad": true}`;单 prompt `{"good": true/false}`。worker 宽容抽取 JSON 解析。

## 数据模型

权威 schema = SQLAlchemy 模型;改 schema 必配编号迁移(铁律)。当前最新迁移 `024`,新增 `025`。

### `prompt_eval_items` 加并行 AI 列(迁移 025)

在 `app/models/prompt_eval.py` 的 `PromptEvalItem` 加列(不动 C2 的人工 verdict 列):

| 列 | 类型 | 说明 |
|---|---|---|
| `ai_winner_arm_id` | int? FK→prompt_eval_arms.id | AI 选的获胜臂 |
| `ai_all_bad` | bool, default False | AI 判「都一样坏」 |
| `ai_is_good` | bool? | 单 prompt AI 判好/坏 |
| `ai_model_id` | int? FK→llm_models.id | 评判模型 |
| `ai_reasoning` | str(Text)? | 评判模型原始回复(展示/排查) |
| `ai_evaluated_at` | datetime? | 已 AI 评估标记(`ai_evaluated := ai_evaluated_at is not None`) |

### 新表 `app_settings`(迁移 025)

通用键值设置表 + `AppSetting` 模型(`app/models/setting.py`,注册 `app/models/__init__.py`):

| 列 | 类型 | 说明 |
|---|---|---|
| `key` | str PK | 设置键(本期 `ai_eval_prompt`) |
| `value` | str(Text) | 设置值 |
| `created_at`/`updated_at` | datetime | `TimestampMixin` |

迁移 `025_ai_evaluation.sql`:`ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ...`(6 列)+ `CREATE TABLE IF NOT EXISTS app_settings (...)`。

**默认评判指令**是代码常量 `DEFAULT_AI_EVAL_PROMPT`(放 `app/services/ai_eval_service.py` 或 `app/ai_eval_defaults.py`),不入库种子。

**计数:表 21→22(新增 app_settings),权限不变(无新增,复用 `llm:manage` 改设置、`prompteval:annotate` 触发)**。更新 `test_migrations_apply` 的 `ntab` 21→22(`nperm` 保持 22);`test_bootstrap` 权限计数不变。

## 评判模型 + 输出契约

- 评判模型 = A 中**启用中的某个 `llm_model`**;其 provider 的 base_url/api_key 已在设置页保存(A),无需另存。
- **可配置项 = 系统指令**(`ai_eval_prompt`,纯文本,无占位符)。worker 自动拼一条 **user 消息**承载该 item 的数据:参数输入 + 候选输出(多臂 = 候选 1..N **按 arm_index 顺序**;单 prompt = 唯一输出)。
- 模型须返回 **JSON**:
  - 多臂:`{"winner": <序号 1..N>}` 或 `{"all_bad": true}`;
  - 单 prompt:`{"good": true|false}`。
- worker 解析:从回复里正则抽第一个 `{...}` 再 `json.loads`;成功则映射 `winner` 序号→`arms[序号-1].id`(越界则留空),写 AI 列;失败(LLMError / 非 JSON / 越界)→ AI 判定列留空,仍写 `ai_reasoning`(原始回复)与 `ai_evaluated_at`(标记已处理,不重复评),并继续下一条。

`DEFAULT_AI_EVAL_PROMPT` 默认内容(可在设置页改):说明「你是严格的评测助手,根据任务输入比较候选回答的质量;多个候选时选出最好的一个或判定都不好,单个候选时判定好坏;**只输出 JSON**,不要多余文字」,并给出上面的 JSON 格式示例。

## 后端 API

### 设置(`app/api/settings.py`,`llm:manage`)

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/settings/ai-eval-prompt` | 返回 `{value}`(库里没有则返回 `DEFAULT_AI_EVAL_PROMPT`) |
| `PUT` | `/settings/ai-eval-prompt` | body `{value}` upsert(写 `app_settings`) |

### 触发 AI 评估(`prompt_eval` 路由,`prompteval:annotate`)

`POST /prompt-evals/{run_id}/ai-evaluate`,body `{model_id}`:
- 校验 run 存在(404)、`model_id` 是有效 `llm_model`(422)。
- 解析当前 `ai_eval_prompt`(库值或默认)。
- `send_prompt_ai_eval_task(run_id, model_id, judge_prompt)` → 写不写 celery id 都行(沿 C1 风格返回 `{"dispatched": true}`)。
- task 名常量 `PROMPT_AI_EVAL_TASK = "modelforge.prompt_ai_eval"` 加到 `modelforge_common/task_names.py`;`celery_client` 加 `send_prompt_ai_eval_task`。

### items 端点扩展

C2 的 `ItemOut` 加 AI 字段:`ai_winner_arm_id`、`ai_all_bad`、`ai_is_good`、`ai_model_id`、`ai_reasoning`、`ai_evaluated_at`。items / verdict 端点构造 `ItemOut` 时一并带上。

`app/services/ai_eval_service.py` 承载:`get_prompt()`(库值或默认)、`set_prompt(value)`、`dispatch(db, run_id, model_id)`(校验 + 解析 prompt + 派发)。

## worker 任务 `modelforge.prompt_ai_eval`

`services/train-worker/worker/prompt_ai_eval.py` 的 `run_prompt_ai_eval(engine, run_id, model_id, judge_prompt)`:
1. 原始 SQL 加载:该 run 的 `eval_type`;模型 creds(`llm_models` join `llm_providers` 取 base_url/api_key/model_str);该 run 的 arms `[(id, arm_index)]`。
2. 取 `ai_evaluated_at IS NULL` 的 items(只评尚未 AI 评的),连同各 item 的 outputs(`output_text` + arm_id),按 arm_index 排出候选顺序。
3. 每条:拼 `messages=[{"role":"system","content":judge_prompt},{"role":"user","content": 渲染的输入+候选}]` → `llm_client.chat(base_url, api_key, model_str, messages)`;抽 JSON 解析:
   - 多臂:`winner`→`arms[winner-1].id` 写 `ai_winner_arm_id`;`all_bad`→`ai_all_bad=true`;
   - 单 prompt:`good`→`ai_is_good`;
   - 写 `ai_model_id`、`ai_reasoning`(原始)、`ai_evaluated_at`(now)。
   - 任何异常/越界 → 仅写 `ai_reasoning` + `ai_evaluated_at`,AI 判定留空,继续。
4. worker DB 助手(原始 SQL,沿 `worker/db.py`):`load_ai_eval_context`、`pending_ai_items`、`set_ai_verdict`。
5. Celery task `prompt_ai_eval_task(run_id, model_id, judge_prompt)` 调 `run_prompt_ai_eval`。

复用 A 的 `llm_client`;顺序调用(YAGNI 不并发)。app-server 与 worker 仍互不 import,仅 DB + 共享 `modelforge_common` 协作。

## 前端

- **设置页(`SettingsPage`)**:新增「AI 评估 Prompt」区块——加载 `GET /settings/ai-eval-prompt` 到 textarea,「保存」调 PUT。`client.ts` 加 `getAiEvalPrompt`/`setAiEvalPrompt`。
- **触发**:`PromptEvalsPage`(succeeded 行)/ 工作台加「AI 评估」入口 → 弹一个小选择(模型来自 `getPromptEvalOptions().models`)→ `POST /prompt-evals/{id}/ai-evaluate {model_id}` → toast「已发起 AI 评估,稍后刷新」;工作台/列表轮询 items 看 AI 结果。
- **展示**:工作台右栏在人工 verdict 区旁加 **AI 评估结果**——AI 选的候选(对照各臂)/好坏 + `ai_reasoning`(折叠)+ 来源徽章(人工 ✓ / AI ✓);`client.ts` 的 `PromptEvalItem` 类型加 AI 字段。
- `client.ts` 加 `triggerAiEval(runId, modelId)`。

## 错误处理

- 触发:run 不存在 404;`model_id` 无效 422;无 pending(未 AI 评)item → 空跑(worker 直接结束)。
- worker:单条 LLMError / JSON 解析失败 / winner 越界 → 不中断,记 `ai_reasoning` + 标 `ai_evaluated_at`,判定列留空。
- 设置:PUT 空值允许(等于清空,GET 回落默认)。

## 测试(TDD)

- **迁移幂等** + 计数(表 21→22,权限不变 22)。
- **设置 service/API**:GET 无库值返回默认、PUT 后 GET 返回新值;`llm:manage` 鉴权 403。
- **触发**:无效 model_id 422;mock `send_prompt_ai_eval_task` 断言派发参数;`prompteval:annotate` 鉴权 403。
- **worker AI 判优**:mock `llm_client.chat` 返回 `{"winner":2}` → 断言对应 item 写 `ai_winner_arm_id=arms[1].id`、`ai_evaluated_at` 非空、`ai_reasoning` 写入;返回非 JSON → 判定列留空但 reasoning/标记写入、不中断;单 prompt 返回 `{"good":true}` → `ai_is_good=true`;只处理 `ai_evaluated_at IS NULL` 的 item。
- **ItemOut 带 AI 字段**;前端 `tsc` + `build`。

## 验收标准

1. 设置页能编辑并保存 AI 评判系统指令;不设置时用内置默认。
2. 对一个 succeeded 评测点「AI 评估」选模型后,worker 异步把未 AI 评的 item 逐条交评判模型判优,JSON 解析后写入 AI 列;单条失败不影响其余。
3. AI 判定与人工 verdict 并存;工作台/列表能看到来源(人工/AI)、AI 选择与 AI 原始推理。
4. 评判模型用 A 中启用的模型(凭证取自设置页);无效模型被拒。
5. `025` 随启动自动应用;全套测试(含真实 PG:22 表 / 22 权限)绿;app-server 与 worker 零互相 import。
