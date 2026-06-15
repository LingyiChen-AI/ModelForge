# 子项目 C2:盲测人工评估工作台 + 每轮统计 — 设计

> 「大模型 Prompt 评测功能」(PRD:[`PRD/prompt-eval.md`](../../../PRD/prompt-eval.md))子项目 **C** 的后半。
>
> 整体:A. LLM 设置页(完成)→ B. Prompt 管理 + Prompt 测试集(完成)→ C1. 评测引擎(完成)→ **C2. 盲测工作台 + 统计**(本文)→ D. AI 自动评估 → E. 统计页。
>
> 接 C1 的数据模型(`prompt_eval_runs/arms/items/outputs`,见 [C1 spec](2026-06-15-prompt-eval-C1-eval-engine-design.md))。

## 目标

让评估人对 C1 跑出的「待评估」输出做**盲测人工评估**(多臂选谁更好 / 单 prompt 逐条好坏),verdict 落库(评估人+时间),并按需算出每轮统计(各 arm 胜率与最优;单 prompt 的好率与变好率/变坏率)。

## 范围

**做**:给 `prompt_eval_items` 加 verdict 列;盲测匿名(后端定序打乱);verdict 提交 API;统计 API(实时);评估工作台(主从两栏)+ 统计展示 + C1 列表入口;`prompteval:annotate` 权限。

**不做**:AI 自动评估(D)、统计页全局聚合(E)、跨 run 的对比看板。

## 关键决策(已与用户确认)

1. **盲测顺序**:每条 item 的各臂输出用 `random.Random(item.id)` 稳定打乱,前端显示为 A/B/C、隐藏 arm 标签;标签仅在统计页揭晓。
2. **单 prompt「上一版数据」**:用 C1 存的 `compare_to_version_id` 找该上一版本**最近一次已评估的** `single_prompt` 运行,按 `(dataset_version_id, row_index)` 匹配同行算变好/变坏率。
3. **统计**:按需实时算(`GET /prompt-evals/{id}/stats`),不预存。
4. **工作台**:复用 badcase 的主从两栏风格。

## 数据模型

权威 schema = SQLAlchemy 模型;改 schema 必配编号迁移(铁律)。当前最新迁移 `022`,新增 `023`(加列)、`024`(权限)。

### `prompt_eval_items` 加列(迁移 023)

在 C1 的 `PromptEvalItem`(`app/models/prompt_eval.py`)上**加列**(不新增表):

| 列 | 类型 | 说明 |
|---|---|---|
| `winner_arm_id` | int? FK→prompt_eval_arms.id | 多臂获胜方(null=未评/all_bad) |
| `all_bad` | bool, default False | 多臂「都一样坏」 |
| `is_good` | bool? | 单 prompt 好/坏(null=未评) |
| `evaluated_by` | int? FK→users.id | 评估人 |
| `evaluated_at` | datetime? | 评估时间(`evaluated := evaluated_at is not None`) |

模型加 `annotator` 关系(`lazy="selectin", viewonly=True, foreign_keys=[evaluated_by]`)+ `annotated_by_name` 属性(复用 badcase 套路)。

迁移 `023_prompt_eval_verdict.sql`:`ALTER TABLE prompt_eval_items ADD COLUMN IF NOT EXISTS ...`(5 列,幂等)。

### 权限(迁移 024)

`024_prompteval_annotate_perm.sql`:新增 `prompteval:annotate`(`看/标注 Prompt 评估`),授予 admin/member;`bootstrap.py` 的 `PERMISSION_CATALOG` 加一条、`BUSINESS` 加 `prompteval:annotate`。**计数:表不变(21),权限 21→22**(更新 `test_bootstrap`→22、`test_migrations_apply` ntab 保持 21 / nperm→22 两处)。

## 盲测匿名(后端定序)

工作台取 items 时,后端对每条 item 的 `outputs` 列表用 `random.Random(item.id)` 做稳定打乱(同 item.id 每次顺序一致),前端按返回顺序渲染为 **A / B / C 卡片,不展示 arm 标签**。verdict 用真实 `arm_id` 提交(前端持有但不显示给评估人)。匿名 = 隐藏标签 + 打乱位置;标签在统计页揭晓。

## 后端 API

### 工作台取数(扩展 C1 的 items 端点)

`GET /prompt-evals/{run_id}/items` 增加:
- query `bucket=pending|evaluated|all`(默认 `all`):`pending` = `evaluated_at IS NULL`,`evaluated` = 反之;分页。
- 返回顺序:每条 item 的 `outputs` 按 `random.Random(item.id)` 打乱。
- `ItemOut` 增加 verdict 字段:`winner_arm_id`、`all_bad`、`is_good`、`annotated_by_name`、`evaluated_at`。
- 权限 `prompteval:read`。

### 提交 verdict

`PATCH /prompt-evals/items/{item_id}/verdict`,权限 `prompteval:annotate`,body `VerdictIn`:
- 多臂 run(`multi_prompt`/`multi_model`):需 `winner_arm_id`(必须属于该 run 的某 arm)**或** `all_bad=true`;二者均无 → 422。设 `winner_arm_id`/`all_bad`,清 `is_good`。
- 单 prompt run:需 `is_good`(bool);设 `is_good`,清 `winner_arm_id`/`all_bad`。
- 统一写 `evaluated_by`=当前用户、`evaluated_at`=now。
- item 不存在 → 404;eval_type 与字段不符 → 422。

`prompt_eval_service`(或新 `prompt_eval_verdict_service`)承载校验 + 落库。

### 统计(实时)

`GET /prompt-evals/{run_id}/stats`,权限 `prompteval:read`,返回:
- 公共:`evaluated`(已评 item 数)、`total`(item 总数)。
- **多臂**:`arms: [{arm_id, label, prompt_version_id, model_id, wins, win_rate}]`(`win_rate = wins / evaluated`,evaluated=0 时 0)、`all_bad`(数)、`best_arm_id`(wins 最多者,平局取 arm_index 小者;evaluated=0 → null)。**揭晓 label**。
- **单 prompt**:`good`、`bad`、`good_rate`;`comparison`:无上一版运行 → null;否则 `{compare_run_id, compare_version_label, comparable, improved, regressed, improved_rate, regressed_rate}`,其中:
  - 找 `compare_to_version_id` 对应版本**最近一次**(id 最大)`single_prompt` 且有已评估 item 的 run;
  - 按 `(dataset_version_id, row_index)` 匹配本 run 与该 run 中**双方都已评估**的 item;
  - `improved` = 上版 `is_good=false` 且本版 `is_good=true` 的数;`regressed` = 上版 true 且本版 false 的数;`comparable` = 匹配上的对数;率 = 数 / comparable(comparable=0 → 0)。

## 前端

### 评估工作台

新页 `frontend/src/pages/PromptEvalWorkbench.tsx`,路由 `/prompt-evals/{id}/evaluate`(`App.tsx` 加正则路由,参考 badcase 工作台的 `/badcase/annotate/:id`)。复用 badcase 主从两栏布局:
- **左**:item 列表,Tab `未评 / 已评 / 全部`(来自 `/items?bucket=`),分页,顶部进度「已评 N / 共 M」。
- **右**:当前 item 的**参数输入**(KV 展示)+ **各臂匿名输出**(A/B/C 卡片,等宽并排或纵向)+ verdict 按钮:
  - 多臂:`A 更好` / `B 更好` / …(按返回的臂数)/ `都一样坏`;
  - 单 prompt:`好` / `坏`(只有一个输出)。
  - 评估人·时间(已评时显示)+ `上一条` / `下一条` / `跳过`;提交即跳下一条。

### 统计 + 入口

- C1 的「Prompt 评测」列表:状态 `succeeded` 的行加 **「评估」**(→ `/prompt-evals/{id}/evaluate`)与 **「统计」** 按钮。
- 统计抽屉(`GET /stats`):多臂展示各 arm(揭晓 label)胜率条 + 最优徽章 + all_bad 数;单 prompt 展示好率 + 变好/变坏率(及对比的上一版本 label)或「无可对比数据」。
- `client.ts` 加:`listPromptEvalItemsPaged(id, {bucket,page,page_size})`(扩展)、`submitPromptEvalVerdict(itemId, body)`、`getPromptEvalStats(id)` 及类型。

## 错误处理

- verdict 与 eval_type 不符 / winner_arm_id 不属于该 run / 二者皆空 → 422 可读。
- item / run 不存在 → 404。
- stats:无已评 item → 计数 0、best_arm_id null;单 prompt 无上一版运行 → `comparison: null`。
- 无 `prompteval:annotate` 不能提交 verdict(403);无 `prompteval:read` 看不到工作台/统计入口(403)。

## 测试(TDD)

- **加列迁移幂等** + 计数(21 表 / 22 权限);`bootstrap` 含 `prompteval:annotate`。
- **verdict service/API**:多臂 winner / all_bad 落库;单 prompt is_good 落库;eval_type 不符 422;winner_arm_id 非本 run 422;`evaluated_by/at` 写入;`prompteval:annotate` 403。
- **stats**:多臂胜率/最优(造 3 臂若干 verdict,断言 wins/win_rate/best);单 prompt 好率;**变好/变坏**(造上一版本一个已评估 run + 本 run,按行匹配,断言 improved/regressed/rates);无上一版 → comparison null。
- **打乱稳定**:同 item.id 两次取 items,outputs 顺序一致;不同 item.id 顺序可不同。
- **bucket 过滤**:pending/evaluated 正确切分。
- 前端 `tsc` + `build`。

## 验收标准

1. 有 `prompteval:annotate` 的用户能在工作台对每条 item 盲测打分(多臂选谁更好/都一样坏;单 prompt 好/坏),记录评估人与时间。
2. 盲测时不展示 arm 标签且各臂位置随机(同条稳定)。
3. 统计页揭晓标签,展示各 arm 胜率与最优;单 prompt 展示好率与对上一版的变好/变坏率(无上一版则提示无数据)。
4. verdict 与 run 类型不符被拒并提示。
5. `023`/`024` 随启动自动应用;bootstrap 与迁移一致;全套测试(含真实 PG:21 表 / 22 权限)绿。
