# 子项目 A:LLM 设置页(模型供应商配置)— 设计

> 本文是「大模型 Prompt 评测功能」(原始 PRD:[`PRD/prompt-eval.md`](../../../PRD/prompt-eval.md))拆分后的**第一个子项目**的设计 spec。
>
> 整体拆分(各自独立交付、独立测试):
> - **A. LLM 设置页(模型供应商配置)** ← 本文,地基
> - B. Prompt 管理 + Prompt 测试集 — 地基
> - C. Prompt 评测引擎 + 三种评测 + 盲测工作台 — 依赖 A + B
> - D. AI 自动评估 — 依赖 C
> - E. 统计页 Prompt 逻辑 — 依赖 C
>
> 构建顺序:A → B → C → D → E。

## 目标

让有权限的用户在「设置」页里配置可调用的大模型供应商(OpenAI 协议),并能一键测试连通性;配置全局共享,供后续 Prompt 评测(子项目 C/D)选用。

## 范围

**做**:供应商 + model-id 的增删改查、连通性测试、掩码存取、RBAC、设置页前端。

**不做**(留给后续子项目):评测时的模型 picker(C)、AI 评估 prompt 的后台设置(D)、被评测引用时的删除保护(C 阶段再加)。

## 关键决策(已与用户确认)

1. **配置粒度**:一条 = 一个**供应商**(`base_url + api_key`),下挂**多个 model-id**;评测时先选供应商再选 model。
2. **API Key**:明文存库,读取时**掩码**(只显示后 4 位);完整值永不返回前端,编辑时留空=不改。
3. **测试按钮**:发**固定探针**(`1+1=? 只回答数字`),走 OpenAI `/chat/completions`,展示模型回复;只验连通+鉴权,**不判正确性**。
4. **权限**:新增权限码 `llm:manage`(可授予,不限超管);配置**全局共享**,无 own/all 数据范围隔离。
5. **技术取舍**:model-id 用**子表**;新建**共享 `llm_client`**(OpenAI 协议 httpx 封装),测试按钮由 app-server **同步直调**(评测 C 复用同一 client)。

## 数据模型

权威 schema = `services/app-server/app/models/` 的 SQLAlchemy 模型;改 schema 必须配编号 SQL 迁移(项目铁律,见 `CLAUDE.md`)。当前最新迁移为 `016_api_key_plaintext.sql`,故新增 `017`、`018`。

### 表 `llm_providers`

| 列 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `id` | int | PK | |
| `name` | str | not null | 展示名 |
| `base_url` | str | not null | OpenAI 协议根,如 `https://api.openai.com/v1` |
| `api_key` | str | not null | 明文存;读取时掩码 |
| `enabled` | bool | default true | 启用/停用 |
| `created_by` | int | FK `users.id`, nullable | 创建者(`CreatorMixin`) |
| `created_at` | datetime | `TimestampMixin` | |

### 表 `llm_models`

| 列 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `id` | int | PK | 稳定主键,供评测(C)引用 |
| `provider_id` | int | FK `llm_providers.id`, **ON DELETE CASCADE**, not null | |
| `model_id` | str | not null | 如 `gpt-4o-mini` |
| `created_at` | datetime | `TimestampMixin` | |
| | | **UNIQUE (`provider_id`, `model_id`)** | 防重 |

### 迁移文件

- `services/app-server/db/migrations/017_llm_providers.sql` — 幂等建两表(`CREATE TABLE IF NOT EXISTS`),含 FK 与唯一约束。
- `services/app-server/db/migrations/018_llm_manage_perm.sql` — `INSERT ... ON CONFLICT DO NOTHING` 加权限 `llm:manage`,并授予系统 admin 角色。
- 同步改 `services/app-server/app/bootstrap.py`:`PERMISSION_CATALOG` 加 `("llm:manage", "LLM 供应商配置")`,`ADMIN_PERMS` 加 `"llm:manage"`(两处与迁移保持一致,铁律)。

## 共享 LLM 客户端

新增 **`services/common/modelforge_common/llm_client.py`**(放 `common`,使 app-server 现在用、worker 在 C 阶段也能复用,不违反「app-server 与 train-worker 互不 import」)。`common` 的 `pyproject.toml` 新增 `httpx` 依赖。

```python
class LLMError(Exception):
    def __init__(self, status: int | None, message: str): ...

@dataclass
class ChatResult:
    content: str
    usage: dict | None
    raw: dict

def chat(base_url: str, api_key: str, model_id: str,
         messages: list[dict], *, timeout: float = 30.0) -> ChatResult:
    """POST {base_url}/chat/completions(OpenAI 协议)。
    成功返回 ChatResult;超时 / 4xx / 5xx / 网络错统一抛 LLMError。"""
```

- URL 拼接:`base_url.rstrip("/") + "/chat/completions"`。
- 请求体:`{"model": model_id, "messages": messages}`。
- 鉴权头:`Authorization: Bearer {api_key}`。
- 解析:`raw["choices"][0]["message"]["content"]`;缺字段也归一化为 `LLMError`。

## 后端 API

新增 router,前缀 `/llm`,`tags=["llm"]`。除非另注,**所有端点需 `llm:manage`**。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `GET` | `/llm/providers` | `llm:manage` | 列表(分页 `paginate` + `X-Total-Count`),每条含 `models[]`,`api_key` 掩码 |
| `POST` | `/llm/providers` | `llm:manage` | 建供应商:`{name, base_url, api_key, model_ids: []}` |
| `PATCH` | `/llm/providers/{id}` | `llm:manage` | 改 `name/base_url/enabled`;`api_key` 留空=不改、给值=重设 |
| `DELETE` | `/llm/providers/{id}` | `llm:manage` | 删供应商(级联删 models) |
| `POST` | `/llm/providers/{id}/models` | `llm:manage` | 加一个 model-id:`{model_id}`;重复 → 422 |
| `DELETE` | `/llm/models/{id}` | `llm:manage` | 删一个 model-id |
| `POST` | `/llm/models/{id}/test` | `llm:manage` | 同步发固定探针,返回 `{ok, reply, latency_ms, error}` |

### 掩码

输出 schema(`ProviderOut`)**不含 `api_key` 字段**,改暴露 `masked_key`(读模型上的 `masked_key` 属性 = `mask_key(api_key)`):长度 ≤ 4 → 单个省略号 `…`(不泄漏任何字符),否则 `key[:3] + "…" + key[-4:]`(如 `sk-…cdef`)。完整 key 不进任何响应 schema。

### 测试端点行为

- 取该 model 的 `provider.base_url / provider.api_key / model.model_id`。
- 探针:`messages=[{"role": "user", "content": "1+1=? 只回答数字"}]`。
- 调 `llm_client.chat(...)`,计时:
  - 成功 → `{"ok": true, "reply": content, "latency_ms": n, "error": null}`。
  - `LLMError` → `{"ok": false, "reply": null, "latency_ms": n, "error": message}`。
- 端点本身始终 HTTP 200(测试结果在 body 的 `ok` 字段),便于前端统一展示。
- 响应仍包在 model-server 之外的 app-server 常规响应里(app-server 不强制 `{code,data,message}` 信封,沿用现有 app-server 风格)。

## 前端 设置页

新增 `frontend/src/pages/SettingsPage.tsx`,路由 `/settings`(在 `App.tsx` 注册);`AppShell` 导航新增「设置」入口(`SlidersHorizontal` 图标),仅 `can("llm:manage")` 显示。

- **供应商表格**:名称、base_url、model 数、状态徽章(启用/停用,复用 `StatusBadge` 风格)、创建者(`Creator`)、操作(编辑 / 删除);服务端分页(引用 `constants.ts` 的 `DEFAULT_PAGE_SIZE`,底部 `Pagination`)。
- **model 列表**:在行内展开区或详情里列出该供应商的 model-id,每行一个「测试」按钮 → 调 `/llm/models/{id}/test`,inline 展示回复(绿)/错误+延迟(红);测试中按钮 loading。
- **新建 / 编辑抽屉**(`Drawer` + `Field` + `Input` + `Button`):name、base_url、api_key(编辑时占位为掩码、留空不改)、可增删多行 model-id。
- API client:`frontend/src/api/client.ts` 新增 `listLlmProvidersPaged / createLlmProvider / updateLlmProvider / deleteLlmProvider / addLlmModel / deleteLlmModel / testLlmModel` 及对应类型。

## 错误处理

- LLM 调用失败:`llm_client` 抛 `LLMError`,测试端点捕获并以 `{ok:false, error}` 返回;前端红字展示可读消息。
- 删除供应商:DB FK `ON DELETE CASCADE` 级联删 models。A 阶段无外部引用;C 阶段再加「被评测引用则禁删」。
- 唯一性:同 provider 下 `model_id` 重复 → 422。
- 安全:完整 `api_key` 永不进响应 schema(只出掩码);`PATCH` 留空不覆盖已存 key。

## 测试(TDD)

测试用 SQLite + `Base.metadata.create_all`(不跑编号 SQL,PG 方言),`conftest.py` 已关 `run_migrations_on_startup`;`bootstrap.seed` 需含 `llm:manage` 以便鉴权测试。

- **`llm_client`**:用 httpx mock(`respx` 或 `httpx.MockTransport`)测:成功解析 `content`;超时 / 4xx / 5xx / 缺字段 → `LLMError`。
- **provider CRUD**:建 / 改 / 删;**掩码不泄漏完整 key**;`PATCH` 留空不改 key、给值改 key;model 增删;唯一约束 422;`enabled` 切换。
- **鉴权**:无 `llm:manage` → 403。
- **测试端点**:mock `llm_client` 成功路返回 `ok:true+reply`、失败路返回 `ok:false+error`。
- **迁移幂等**:`017`/`018` 重复执行不报错(若有 PG 环境的迁移测试,沿用现有做法)。

## 验收标准

1. 有 `llm:manage` 的用户能在设置页新建供应商(填 base_url / api_key / 多个 model-id)、编辑、删除、启停。
2. 列表与详情里 api_key 始终掩码;编辑留空不会清空已存 key。
3. 点某 model 的「测试」按钮,能看到该模型对固定探针的真实回复(连通成功)或可读错误(失败)。
4. 无 `llm:manage` 的用户看不到「设置」入口,直接调管理端点返回 403。
5. `017`/`018` 迁移随 app 启动自动应用;`bootstrap.py` 与迁移的权限目录一致。
