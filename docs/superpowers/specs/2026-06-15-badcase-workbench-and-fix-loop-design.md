# Badcase 列表重构 + 修复闭环 设计

**日期:** 2026-06-15
**状态:** 已确认,待实现

## 目标

把 Badcase 页从「按模型版本分组堆原始坏例」改成**模型汇总表 + 全页标注工作台**;
并打通**修复闭环**:badcase 训练后用新模型回测,给被修复的 badcase 打上 `V4 已修复` 标签,
并在该次训练的模型指标里加一个 `badcase 修复率`。

## 决策(来自 brainstorming)

1. **修复率范围** = 本次训练实际用到的 badcase(其 `dataset_version_id` 属于该训练的 train 版本)。
2. **判定执行** = 训练完成后,worker 用刚训好的新模型直接推理判定(模型还在磁盘 temp dir 时)。
3. **标注工作台形态** = 全页逐条工作台。

---

## Part A — 列表页改为「模型汇总 + 标注工作台」

### A1. 列表页(汇总表)

每行 = 一个有 badcase 的 `model_version`:

| 列 | 来源 |
|---|---|
| 模型名称 · 版本 | `model_version.name` + `mlflow_version` |
| 类型 | `task_type`(中文映射:分类/序列标注/句对/向量检索) |
| 上报数量 | 该 model_version 下 badcase 总数 |
| 已标注数量 | `status IN ('annotated','used')` 的数量 |
| 已生成训练集 | `status='used'` 的数量 |
| 操作 | 「标注」→ 工作台;「查看」→ 该模型的原始 badcase 列表(沿用现有筛选视图) |

**新后端端点:** `GET /badcases/summary`
- 权限:`require("badcase:read")`
- 返回 `list[BadcaseSummaryOut]`,每项:
  ```json
  {
    "model_version_id": 1,
    "model_name": "客服意图分类",
    "model_version_label": "3",
    "task_type": "classification",
    "reported": 24,        // 总数
    "annotated": 18,       // annotated + used
    "used": 12,            // 已生成训练集
    "pending": 6,          // 待标注(status='reported')
    "fixed": 9             // fixed_by 非空的数量
  }
  ```
- 实现:对 `badcases` 按 `model_version_id` 聚合计数(SQLAlchemy `func.count` + `case`)。
  无 badcase 的模型不出现在列表里。

### A2. 标注工作台(新全页路由)

- 路由:`/badcase/annotate/:modelVersionId`(前端 router 注册)。
- 数据加载:复用 `GET /badcases?model_version_id=X&status=reported` 取待标注队列;
  另取该 model_version 的汇总用于进度展示。
- 布局:
  - 顶部:模型名 · 版本 + 进度「已标注 X / 待标注 Y」+ 返回汇总页按钮。
  - 主体:**逐条**展示当前待标注 badcase:
    - 输入(按 task_type 渲染:分类=文本;序列标注=tokens;句对=text_a/text_b;向量=query+candidates)。
    - 模型推理(对照展示 `inference`)。
    - 标注表单(按 task_type)。
  - 提交标注 → `PATCH /badcases/{id}/annotate` → 成功后自动加载下一条;队列空显示「全部标注完成」。
  - 工作台保留「用已标注的生成 `badcase-` 训练集」(复用 `POST /badcases/build-dataset`,默认选中本模型全部已标注未使用的)。
- **复用:** 把现有 `BadcaseAnnotateDrawer` 里的「按 task_type 的标注表单」抽成独立组件
  `BadcaseAnnotateForm`(输入展示 + 表单 + 校验),工作台和(保留的)抽屉都用它。

### A3. 保留入口

- 「查看」按钮进入的原始 badcase 列表沿用现有页面逻辑(筛选 + StatusBadge),
  但展示已修复标签(见 B4)。不再作为默认首屏。

---

## Part B — 修复闭环

### B1. 数据模型

**`Badcase` 新增列 `fixed_by`(JSON,默认 `[]`):**
```python
fixed_by: Mapped[list] = mapped_column(JSON, default=list)
```
- 元素:`{"model_version_id": 5, "version_label": "4", "at": "2026-06-15T10:00:00Z"}`。
- 非空 = 已修复。一个 badcase 可被多个版本修复(V4、V7),append 累积,同 `model_version_id` 去重。
- `BadcaseOut` schema 增加 `fixed_by: list = []`。

**迁移 `db/migrations/015_badcase_fixed_by.sql`:**
```sql
ALTER TABLE badcases ADD COLUMN IF NOT EXISTS fixed_by JSON DEFAULT '[]'::json;
```
- 幂等。无新表、无新权限 → `test_migrations_apply` 的表数/权限数断言**不变**。
- `app/bootstrap.py` 无需改(无新权限)。

**`ModelVersion.train_metrics`(已是 JSON):** 新增 key `badcase_fix_rate`(float)。无需迁移。

### B2. worker 修复判定

**新模块 `services/train-worker/worker/badcase_scoring.py`:**
```python
def score(task_type: str, model_dir: str, rows: list[dict]) -> list[bool]:
    """对每个 badcase 行用 model_dir 的模型推理,返回是否已修复(预测==标注)。
    row = {"input": {...}, "annotation": {...}}。"""
```
- 逐 task_type 实现正确性判定:
  - `classification`:加载模型预测 `input.text` 的 label → == `annotation.label`。
  - `ner`:预测 `input.tokens` 的 tag 序列 → 与 `annotation.tags` 逐位相等(长度也相等)。
  - `pair`:预测 `input.text_a/text_b` 的 label → == `annotation.label`。
  - `embedding`:对 `input.query` 与 `input.candidates` 编码、按相似度重排,top-1 ∈ `annotation.pos`。
- 复用 evaluators 已有的模型加载方式(transformers / sentence-transformers),
  但返回**逐行**布尔,而非聚合指标。空 `rows` 返回 `[]`。

**`worker/db.py`:** `load_job` 在返回 dict 里补 `row["train_version_ids"] = train_ids`,
供 task 查询本次训练用到的 badcase。

**`worker/tasks.py` `train_task`(在 `with tempfile.TemporaryDirectory() as out:` 块内、
模型产物还在 `out` 时):**
```python
# 训练成功、模型已落到 result.artifact_dir 后:
bc_rows = load_trained_badcases(engine, job["train_version_ids"])  # 查 badcases
if bc_rows:
    fixed = badcase_scoring.score(job["task_type"], result.artifact_dir,
                                  [{"input": r["input"], "annotation": r["annotation"]} for r in bc_rows])
    fix_rate = sum(fixed) / len(fixed)
    result.metrics["badcase_fix_rate"] = fix_rate
    fixed_ids = [r["id"] for r, ok in zip(bc_rows, fixed) if ok]
```
- `load_trained_badcases(engine, version_ids)`:`SELECT id, input, annotation FROM badcases
  WHERE dataset_version_id IN :ids AND annotation IS NOT NULL`(worker/db.py)。
- 把 `fixed_ids`、新版本 label 随结果回报(见 B3)。若 `bc_rows` 为空,不加 `badcase_fix_rate`,
  写回也跳过(完全不影响普通训练)。
- 评分失败不应让训练任务失败:try/except 包裹,失败仅记日志、跳过写回。

### B3. 写回(经 app-server)

**worker `report_result` payload 扩展(可选字段):**
```json
{
  "...": "...",
  "badcase_fixes": [12, 15, 19],          // 被修复的 badcase id
  "badcase_fix_version": "4",             // 新模型版本 label
  "badcase_fix_model_version_id": 5
}
```

**app-server 内部结果端点 `POST /training-jobs/internal/{id}/result`:**
- `TrainResultIn` schema 增加可选 `badcase_fixes: list[int] = []`、
  `badcase_fix_version: str | None = None`、`badcase_fix_model_version_id: int | None = None`。
- 处理:`metrics`(含 `badcase_fix_rate`)照常写新版本 `train_metrics`;
  对 `badcase_fixes` 里每个 badcase,给 `fixed_by` append
  `{model_version_id, version_label, at=now}`(同 `model_version_id` 已存在则跳过)。
- 抽到 `badcase_service.mark_fixed(db, badcase_ids, model_version_id, version_label)`。

### B4. UI 展示

- 汇总页:`fixed` 列(或在「已标注」旁标注)。
- 标注工作台 + 原始 badcase 列表:有 `fixed_by` 的显示 `V4 已修复`、`V7 已修复` 标签(Badge,绿色)。
- 模型详情时间轴的结果指标:若该训练含 badcase,多出 `badcase 修复率`(百分比展示)。

---

## 文件清单

**app-server**
- 改 `app/models/badcase.py`(加 `fixed_by`)
- 新 `db/migrations/015_badcase_fixed_by.sql`
- 改 `app/schemas/badcase.py`(`BadcaseOut.fixed_by`;新 `BadcaseSummaryOut`)
- 改 `app/api/badcase.py`(新 `GET /badcases/summary`)
- 改 `app/services/badcase_service.py`(新 `summary(db)`、`mark_fixed(...)`)
- 改 `app/api/training.py` + `app/schemas/training.py`(`TrainResultIn` 扩展、写回)

**train-worker**
- 新 `worker/badcase_scoring.py`
- 改 `worker/db.py`(`load_job` 加 `train_version_ids`;新 `load_trained_badcases`)
- 改 `worker/tasks.py`(`train_task` 评分 + 回报)

**frontend**
- 改 `src/pages/BadcasePage.tsx`(汇总表)
- 新 `src/pages/BadcaseAnnotateWorkbench.tsx`(全页工作台)
- 新/改 `src/pages/BadcaseAnnotateForm.tsx`(从 Drawer 抽出的复用表单)
- 改 `src/App.tsx` / router(新路由)
- 改 `src/api/client.ts`(`listBadcaseSummary`;`Badcase.fixed_by` 类型)
- 改模型详情时间轴指标展示(`badcase_fix_rate` → 「badcase 修复率」百分比)

## 测试

- worker:`test_badcase_scoring.py` —— 四类各一个对/错样本,断言逐行布尔正确。
- app-server:
  - `test_badcase_summary` —— 造数据,断言聚合计数。
  - `test_mark_fixed` —— `report_result` 带 `badcase_fixes` 时 `fixed_by` 正确 append + 去重。
  - `test_migrations_apply` —— 表数/权限数断言不变(只加列)。
- 不改现有训练/评估主流程契约;`badcase_fix_rate` 只在含 badcase 训练时出现。
