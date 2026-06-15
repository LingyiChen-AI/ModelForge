# 子项目 C1:Prompt 评测引擎 + 三种评测 + 数据模型 — 设计

> 「大模型 Prompt 评测功能」(PRD:[`PRD/prompt-eval.md`](../../../PRD/prompt-eval.md))的第三个子项目 **C** 的前半。
>
> 整体拆分:A. LLM 设置页(完成)→ B. Prompt 管理 + Prompt 测试集(完成)→ **C. 评测**(C1 引擎+三种评测+数据模型【本文】→ C2 盲测工作台+统计)→ D. AI 自动评估 → E. 统计页。
>
> C 因体量拆为 C1 / C2:**C1** 把运行引擎、数据模型、三种评测的提交/派发/worker 跑出「待评估」输出做透;**C2** 接人工盲测评估台 + 统计。本文 = C1。

## 目标

让用户发起三种 Prompt 评测(多 prompt 盲测 / 多模型盲测 / 单 prompt 版本对比),由 worker 调用大模型批量产出结果(状态=待评估),为 C2 的人工评估与统计备好数据。

## 范围

**做**:统一的评测数据模型(run / arm / item / output);提交校验(prompt 参数 ⊆ 测试集字段)+ 派发;worker 渲染模板、调 LLM、写输出、报进度;`prompt_template.render`(B 遗留补上);RBAC;前端「新建评测」三类型表单 + 运行列表(进度)。

**不做**(留给 C2):盲测匿名展示、人工 verdict(谁更好 / 好坏)落库、每轮统计(各 arm 胜率、最优、单 prompt 变好率/变坏率)、AI 自动评估(D)。

## 关键决策(已与用户确认)

1. **拆分**:C → C1(引擎+数据模型)+ C2(工作台+统计);先做 C1。
2. **判定语义**(C2 落地,C1 数据模型预留):多 prompt / 多模型 = 每条测试行盲选「谁更好 / 都一样坏」;单 prompt = 每条输出标「好/坏」再与上一版本比算变好率/变坏率。

## 数据模型

权威 schema = SQLAlchemy 模型;改 schema 必配编号 SQL 迁移(铁律)。当前最新迁移 `020_prompt_perms.sql`,新增 `021`、`022`。

### 表 `prompt_eval_runs`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `name` | str | 时间戳自动命名(前端 `tsName()` 生成,`yyyyMMddHHmmss`) |
| `eval_type` | str | `multi_prompt` / `multi_model` / `single_prompt` |
| `status` | str | `JobStatus`(pending/running/succeeded/failed) |
| `progress` | float | 0~1 |
| `celery_task_id` | str | nullable |
| `error` | str | nullable |
| `prompt_version_ids` | JSON | 参与的 prompt 版本 id 列表 |
| `model_ids` | JSON | 参与的 llm_model id 列表(A 的子表主键) |
| `dataset_version_ids` | JSON | prompt 测试集版本 id 列表 |
| `compare_to_version_id` | int? | 单 prompt:上一版本 prompt_version_id;否则 null |
| `result_summary` | JSON | 默认 `{}`,C2 填统计 |
| `created_by` | int? FK users | `CreatorMixin` |
| `created_at`/`updated_at` | datetime | `TimestampMixin` |

### 表 `prompt_eval_arms`(被盲测对比的对象)

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `run_id` | int FK→prompt_eval_runs `ON DELETE CASCADE` | |
| `arm_index` | int | 0/1/2 → A/B/C |
| `prompt_version_id` | int FK→prompt_versions | 该臂用的 prompt 版本 |
| `model_id` | int FK→llm_models | 该臂用的模型 |
| `label` | str | 展示名(如「问候 V2」或「gpt-4o-mini」);盲测时前端不展示,揭晓用 |

- 多 prompt:N prompt 版本 × 固定 1 模型 → N 臂(`label`=prompt 名+版本)。
- 多模型:固定 1 prompt 版本 × N 模型 → N 臂(`label`=模型 model_id)。
- 单 prompt:1 臂(该 prompt 版本 × 1 模型)。

### 表 `prompt_eval_items`(测试集每行)

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `run_id` | int FK→prompt_eval_runs `ON DELETE CASCADE` | |
| `item_index` | int | 跨多测试集展平后的序号 |
| `dataset_version_id` | int | 该行来自哪个测试集版本 |
| `row_index` | int | 在该测试集内的行号 |
| `inputs` | JSON | 该行的参数→值映射(渲染模板用) |

> C2 将在本表追加 verdict 字段(winner_arm_id / is_good / status / evaluated_by / evaluated_at)——C1 不建这些列,迁移由 C2 负责。

### 表 `prompt_eval_outputs`(一个臂对一条 item 的产出)

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `item_id` | int FK→prompt_eval_items `ON DELETE CASCADE` | |
| `arm_id` | int FK→prompt_eval_arms | |
| `output_text` | Text | 模型输出;default `''` |
| `status` | str | `pending` / `done` / `error`,default `pending` |
| `error` | str? | LLM 调用失败信息 |
| `latency_ms` | int | default 0 |

ORM 关系都用 `lazy="selectin"` + 父向子 `cascade="all, delete-orphan"`;迁移用 FK `ON DELETE CASCADE`。

### 迁移文件

- `021_prompt_evals.sql` — 幂等建 4 表(FK CASCADE、索引 `run_id`/`item_id`)。
- `022_prompteval_perms.sql` — `prompteval:read`/`prompteval:run`,授予:read→admin/member/viewer,run→admin/member。
- `bootstrap.py`:`PERMISSION_CATALOG` 加两条;`READS` 加 `prompteval:read`;`BUSINESS` 加 `prompteval:run`。计数断言同步(+4 表 / +2 权限)。

## 共享模板渲染(补 B 的遗留)

在 `services/common/modelforge_common/prompt_template.py` 增加:

```python
def render(template: str, values: dict) -> str:
    """把 {{ name }} 替换为 str(values.get(name, ""))。未知参数 → 空串。"""
```

实现:复用已有的参数正则,`re.sub` 回调里取 `values.get(name)`,`None`/缺失 → `""`,否则 `str(value)`。

## 提交校验 + 派发(app-server)

`POST /prompt-evals`,body `PromptEvalCreate`:`eval_type`、`name`、`prompt_version_ids: list[int]`、`model_ids: list[int]`、`dataset_version_ids: list[int]`。

**按类型的数量约束**(违反 → 422):
- `multi_prompt`:`len(prompt_version_ids) >= 2`、`len(model_ids) == 1`、`len(dataset_version_ids) >= 1`。
- `multi_model`:`len(prompt_version_ids) == 1`、`len(model_ids) >= 2`、`len(dataset_version_ids) >= 1`。
- `single_prompt`:`len(prompt_version_ids) == 1`、`len(model_ids) == 1`、`len(dataset_version_ids) >= 1`。

**参数校验**:取所有涉及的 prompt 版本的 `params` 并集,对每个测试集版本读 `DatasetVersion.stats["columns"]`,若有 param 不在某测试集的列里 → 422 `"测试集〈name V{no}〉缺少参数 {p}"`。

**派发**:校验通过 → 建 `PromptEvalRun` + 按类型生成 `PromptEvalArm`(arms=变化维度的笛卡尔)→ `send_task("modelforge.prompt_eval", [run_id])`,写 `celery_task_id`。`single_prompt` 时查同一 prompt 下 `version_no` 小于当前且最大的版本,存 `compare_to_version_id`(无则 null)。

`services/app-server/app/services/prompt_eval_service.py` 承载校验 + 建模 + 派发;`app/celery_client.py` 加 `send_prompt_eval_task`(module-level,可 monkeypatch)。task 名常量 `PROMPT_EVAL_TASK = "modelforge.prompt_eval"` 加到 `services/common/modelforge_common/task_names.py`。

## worker 任务 `modelforge.prompt_eval`

`services/train-worker/worker/tasks.py` 新增 task(name=`PROMPT_EVAL_TASK`):
1. `set` run RUNNING、progress 0.02。
2. load run(eval_type、arms[(id, arm_index, prompt_version_id, model_id, system_prompt, user_prompt)]、dataset_version_ids 及各自 storage_uri、各 arm 模型的 base_url/api_key/model_id)。worker DB 助手用原始 SQL(沿 `worker/db.py` 风格)。
3. 读各测试集快照(`read_snapshot`),展平成 items;为每个 item 写一行 `prompt_eval_items`,并为每个 arm 写一行 `prompt_eval_outputs(status=pending)`。
4. 逐个 output:`render(system_prompt, inputs)` + `render(user_prompt, inputs)` → `messages=[{"role":"system",...},{"role":"user",...}]`(system 为空则省略)→ `llm_client.chat(base_url, api_key, model_id, messages)`;成功写 `output_text`/`latency_ms`/`status=done`,`LLMError` 写 `error`/`status=error`(**不中断整轮**)。progress 按已完成 output 比例更新。
5. 全部完成 → run `succeeded`、progress 1.0。加载/致命异常 → run `failed`(error)。

顺序调用(I/O 密集;并发是后续优化,YAGNI)。worker 复用 `modelforge_common.llm_client`(A)与 `modelforge_common.prompt_template`(B)。

## 后端 API

router `/prompt-evals`,`tags=["prompt-evals"]`:

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `GET` | `/prompt-evals` | `prompteval:read` | 列表(分页 + `X-Total-Count`,带 eval_type/status/progress) |
| `POST` | `/prompt-evals` | `prompteval:run` | 提交(见上),返回 run |
| `GET` | `/prompt-evals/{id}` | `prompteval:read` | run + arms + 进度 |
| `GET` | `/prompt-evals/{id}/items` | `prompteval:read` | items + 各 arm 的 outputs(分页);**C1 返回原始 label/输出**,盲测匿名留 C2 |

## 前端

新页 `frontend/src/pages/PromptEvalsPage.tsx`(路由 `/prompt-evals`,导航「Prompt 评测」,`prompteval:read` 可见):
- 运行列表:名称、类型(中文)、状态徽章、进度条、创建者、时间;服务端分页;**轮询刷新进度**(沿用现有列表轮询)。
- 「新建评测」抽屉:先选 `eval_type`(三选一),按类型显示对应表单:
  - 多 prompt:多选 prompt 版本(下拉来自 `/prompts` + 版本)+ 选 1 模型(A 的 llm_models,按供应商分组,复用 `taskGroups`/新分组)+ 多选 prompt 测试集版本;
  - 多模型:选 1 prompt 版本 + 多选模型 + 多选测试集;
  - 单 prompt:选 1 prompt 版本 + 1 模型 + 多选测试集。
  - 前端做数量约束,后端做参数校验;name 用 `tsName()` 自动填(可改)。
- `client.ts` 加 `listPromptEvalsPaged / createPromptEval / getPromptEval / listPromptEvalItemsPaged` 与类型;模型 picker 需要一个「启用中的 llm 模型」只读列表 API —— 复用/新增 `GET /llm/models?enabled=1`(A 阶段预留,这里落地一个登录可读的精简列表)。
- `AppShell` 导航加「Prompt 评测」入口(`ClipboardCheck` 图标,`prompteval:read`)。

> 备注:A 的 `/llm/providers` 需 `llm:manage`,评测发起者未必有该权限。本子项目落地一个**登录可读**的精简模型列表 `GET /llm/models`(返回启用供应商下的 `{id, model_id, provider_name}`),供评测 picker 用。

## 错误处理

- 提交:类型数量不符、参数不匹配、空测试集 → 422 可读中文。
- 单条 LLM 失败:output 记 `error`/`status=error`,继续跑;run 不因单条失败而 failed。
- run 加载/快照读失败 → run `failed` + error。
- 删除 run:级联删 arms/items/outputs(FK CASCADE + ORM delete-orphan)。

## 测试(TDD)

- **`render`**(common):基本替换、缺参数→空、数字/None 值、多参数。
- **提交校验**(service):三类型数量约束、参数⊆字段通过、缺参数 422 文案、arms 生成正确(多 prompt N 臂、多模型 N 臂、单 prompt 1 臂 + compare_to_version_id)。
- **worker 任务**:mock `llm_client.chat`,跑一个小 run(1 测试集 2 行 × 2 臂),断言 items=2、outputs=4 且 `status=done`、`output_text` 写入、progress 到 1.0、run succeeded;再 mock 一条抛 `LLMError`,断言该 output `status=error` 且 run 仍 succeeded。
- **API**:提交→列表→详情→items;`prompteval:read`/`prompteval:run` 鉴权 403;`GET /llm/models` 登录可读。
- **迁移幂等** + 计数断言(+4 表 / +2 权限)。

## 验收标准

1. 有 `prompteval:run` 的用户能发起三种评测;参数与测试集字段不匹配时被拒并提示缺哪个参数。
2. 提交后 worker 异步把测试集每行 × 每臂调用大模型,产出 outputs(`status=done`/`error`),run 进度可见、最终 succeeded。
3. 单条模型调用失败不影响整轮;run 详情能看到 arms 与每条 item 的各臂输出(C1 原始展示)。
4. 单 prompt 评测会记录 `compare_to_version_id`(上一版本)。
5. 无 `prompteval:read` 的用户看不到「Prompt 评测」入口,直接调 API 返回 403。
6. `021`/`022` 随启动自动应用;bootstrap 与迁移一致;全套测试(含真实 PG 计数)绿。
