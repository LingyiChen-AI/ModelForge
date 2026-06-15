# 子项目 B:Prompt 管理 + Prompt 测试集 — 设计

> 「大模型 Prompt 评测功能」(PRD:[`PRD/prompt-eval.md`](../../../PRD/prompt-eval.md))拆分后的**第二个子项目**。
>
> 整体拆分:A. LLM 设置页(已完成)→ **B. Prompt 管理 + Prompt 测试集**(本文)→ C. 评测引擎+三种评测+盲测工作台 → D. AI 自动评估 → E. 统计页 Prompt 逻辑。

## 目标

让用户管理带 `{{ 参数 }}` 模板的 Prompt(system + user,版本化),并维护「Prompt 测试集」(列即参数),为后续评测(C/D)提供 prompt 与测试数据。

## 范围

**做**:Prompt + 版本的增删查、`{{参数}}` 语法校验与参数抽取、Prompt 测试集(新数据集类型)的创建与上传、RBAC、前端 Prompt 页与数据集页的 prompt 类型集成、供 C 复用的共享模板工具(extract + validate)。

**不做**(留给后续):模板渲染 `render(template, values)`(C 评测时填参)、prompt 参数与测试集字段的「一一对应」匹配校验(发生在 C 的评测提交)、被评测引用时的删除保护(C)。

## 关键决策(已与用户确认)

1. **Prompt 测试集存储**:复用现有 `datasets`/`dataset_versions` 表,新增 `DatasetKind.PROMPT="prompt"`;不走固定 task_type 列校验,改把各列名(=参数)记进版本 `stats`。
2. **Prompt 版本模型**:`prompts` + `prompt_versions` 两表,版本不可变。
3. **参数语法**:`{{ name }}` 双花括号(两边空格可选、自动 trim);`name` 允许字母/数字/下划线/中文;保存时校验。
4. **权限**:新增 `prompt:read` / `prompt:write`;Prompt 测试集复用 `dataset:read` / `dataset:write`。

## 数据模型

权威 schema = SQLAlchemy 模型;改 schema 必须配编号 SQL 迁移(铁律,见 `CLAUDE.md`)。当前最新迁移 `018_llm_manage_perm.sql`,故新增 `019`、`020`。

### 表 `prompts`

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | int | PK | |
| `name` | str | not null | Prompt 展示名 |
| `created_by` | int | FK users.id, nullable | `CreatorMixin` |
| `created_at` / `updated_at` | datetime | `TimestampMixin` | |

`versions` 关系:`lazy="selectin"`, `cascade="all, delete-orphan"`, `back_populates="prompt"`。

### 表 `prompt_versions`

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | int | PK | |
| `prompt_id` | int | FK prompts.id `ON DELETE CASCADE`, not null | |
| `version_no` | int | not null | 自增,`UNIQUE(prompt_id, version_no)` |
| `system_prompt` | str(Text) | not null, default "" | 含 `{{参数}}` 模板 |
| `user_prompt` | str(Text) | not null, default "" | 含 `{{参数}}` 模板 |
| `params` | JSON | default list | 保存时从 system+user 抽出的参数名(并集、去重保序) |
| `note` | str | default "" | |
| `created_by` | int | FK users.id, nullable | |
| `created_at` / `updated_at` | datetime | | |

### Prompt 测试集(复用 datasets)

- `DatasetKind.PROMPT = "prompt"` 加入 `services/common/modelforge_common/enums.py`。
- prompt 数据集:`Dataset(kind="prompt", task_type="prompt")`(`task_type` 列是 str,存字面量,不进 `TaskType` 枚举,因此不会出现在训练/评估的 task 选择里)。
- 上传版本时:**跳过** `validate_rows(task_type)` 的固定列校验,改为校验「至少一列、至少一行」,并把列名写进该版本的 `stats={"columns": [...]}`。

### 迁移文件

- `019_prompts.sql` — 幂等建 `prompts` / `prompt_versions`(FK CASCADE、UNIQUE、索引)。
- `020_prompt_perms.sql` — `INSERT ... ON CONFLICT DO NOTHING` 加 `prompt:read` / `prompt:write`,授予:`prompt:read`→admin/member/viewer,`prompt:write`→admin/member。
- 同步改 `app/bootstrap.py`:`PERMISSION_CATALOG` 加两条;`READS` 加 `prompt:read`、`BUSINESS` 加 `prompt:write`(与现有 reads/business 组织一致)。

## 共享模板工具

新增 **`services/common/modelforge_common/prompt_template.py`**(放 common,C 的 worker 复用):

```python
PARAM_RE = ...  # 匹配 {{ name }}

def extract_params(text: str) -> list[str]:
    """抽出全部 {{ name }} 的 name(trim),去重保序。"""

def validate_template(text: str) -> list[str]:
    """返回错误消息列表(空=合法)。检测:
    - 花括号不成对(落单的 {{ 或 }})
    - 空参数名 {{ }}
    - 嵌套 {{ {{ }} }}
    - 非法字符(name 必须匹配 [\\w\\u4e00-\\u9fff]+)
    """
```

- `name` 合法字符集:`[\w一-鿿]+`(下划线/字母/数字/中文)。
- `render(template, values)` 留给子项目 C,本子项目不建。
- Prompt 一条记录的「参数」= `extract_params(system_prompt) ∪ extract_params(user_prompt)`(并集、保序)。

## 后端 API

### Prompt(router `/prompts`)

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `GET` | `/prompts` | `prompt:read` | 列表(分页 `paginate` + `X-Total-Count`),每条带最新版本号与参数 |
| `POST` | `/prompts` | `prompt:write` | 建 Prompt + 首版本:`{name, system_prompt, user_prompt, note?}`;先 `validate_template` 两段,有错 422;抽参数存版本 |
| `GET` | `/prompts/{id}` | `prompt:read` | 详情 + 版本列表 |
| `GET` | `/prompts/{id}/versions` | `prompt:read` | 版本列表(分页) |
| `POST` | `/prompts/{id}/versions` | `prompt:write` | 新增版本:`{system_prompt, user_prompt, note?}`;校验+抽参数;`version_no = max+1` |
| `POST` | `/prompts/validate` | `prompt:read` | 预览:`{system_prompt, user_prompt}` → `{params: [...], errors: [...]}`,给编辑器实时反馈 |

### Prompt 测试集(datasets 域)

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `POST` | `/datasets/prompt` | `dataset:write` | 建 prompt 数据集:`{name}` → `Dataset(kind="prompt", task_type="prompt")` |
| `POST` | `/datasets/{id}/versions` | `dataset:write` | **复用现有端点**;`dataset_service` 内按 `dataset.kind` 分支:prompt 集跳过固定列校验,改校验≥1列≥1行 + 把列名写进 `stats.columns` |
| 列表/版本/下载 | 复用现有 | | datasets 页按 `kind=prompt` 过滤 |

## 前端

- **新页 `frontend/src/pages/PromptsPage.tsx`(路由 `/prompts`,导航「Prompt」,`prompt:read` 可见)**:
  - 列表:名称、最新版本号、参数 chips、创建者、创建时间;服务端分页。
  - 新建/编辑抽屉:`name` + system / user 两段 `<textarea>` 编辑器;输入时(防抖)调 `POST /prompts/validate`,实时显示**抽到的参数 chips** 与**语法错误**;保存 = 新建 Prompt(或对已有 Prompt 新增版本)。
  - 详情:版本历史(version_no / 参数 / 时间 / 创建者)。
- **Prompt 测试集**并入现有数据集页:`kind` 增加 `prompt`(筛选 + 新建);prompt 集的新建/上传不选 task_type、不下载固定模板,上传后展示识别出的列(=参数)。
- `frontend/src/api/client.ts` 加:`listPromptsPaged / createPrompt / getPrompt / listPromptVersionsPaged / addPromptVersion / validatePrompt` 及类型;`createPromptDataset`。
- 数据集 kind 文案(`taskGroups.ts` 或数据集页常量)加 `prompt → "Prompt 测试集"`。
- `AppShell` 导航加「Prompt」入口(`MessageSquareText` 图标,`prompt:read`)。

## 错误处理

- 模板语法错误:`validate_template` 返回可读中文错误;`POST /prompts`、`/prompts/{id}/versions` 校验失败 422,前端就近红字。
- prompt 测试集上传:空文件 / 零列 → 422(`"Prompt 测试集至少需要一列参数"`);保留现有 CSV/JSONL/Excel 解析。
- Prompt 删除(若提供):级联删版本(FK CASCADE + ORM delete-orphan);被评测引用的保护留到 C。
- 参数抽取:system + user 取并集,重复只记一次,保序。

## 测试(TDD)

测试用 SQLite + `create_all`;`bootstrap.seed` 含新权限。

- **`prompt_template`**(common):`extract_params` 正常 / 多参数 / 中文名 / 去重 / 无参数→`[]`;`validate_template` 捕获不成对、空名 `{{ }}`、嵌套、非法字符;合法模板→`[]`。
- **Prompt CRUD**:建 Prompt+首版本、加版本 `version_no` 自增、`params` 落库正确(system∪user)、语法错误 422、`prompt:write` 鉴权 403、`/prompts/validate` 返回 params+errors 两路。
- **Prompt 测试集**:`POST /datasets/prompt` 建集(kind/task_type 正确);上传版本把列名写进 `stats.columns`、跳过固定列校验、零列 422;`dataset:read/write` 鉴权。
- **迁移幂等**;新表(13/15→+2)与新权限计数断言同步更新(参考 A 的 `test_bootstrap` / `test_migrations_apply`)。

## 验收标准

1. 有 `prompt:write` 的用户能建 Prompt(填 system/user 模板)、新增版本;非法 `{{` 语法被拒并给出可读错误。
2. 编辑时能实时看到抽出的参数(system∪user)。
3. Prompt 版本不可变、`version_no` 自增,详情可见历史。
4. 能建「Prompt 测试集」并上传 CSV/JSONL,其列被识别为参数并存进版本 `stats.columns`;空列被拒。
5. 无 `prompt:read` 的用户看不到「Prompt」入口,直接调 `/prompts` 返回 403。
6. `019`/`020` 随启动自动应用;`bootstrap.py` 与迁移权限目录一致;全套测试(含真实 PG 迁移计数)绿。
