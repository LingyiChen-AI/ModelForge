# Badcase 上报与修复闭环 — 设计文档

**日期:** 2026-06-14
**状态:** 待评审
**作者:** liuqinghe (with Claude)

## 1. 目标

让外部业务系统把模型在线上犯的错(badcase)通过 API 上报到 ModelForge;平台按**模型版本**自动归类、记录输入与模型推理输出;团队在系统内对 badcase 做**标注**(补正确答案);把标注后的 badcase 一键生成一个带 `badcase-` 前缀的训练集;再选模型用它训练新版本完成**修复**——形成 “上线 → 发现 badcase → 上报 → 标注 → 重训 → 修复” 的闭环。

同时落地一套**通用 API Key 体系**:既给 badcase 上报接口鉴权,也给目前**裸奔无鉴权**的 model-server 在线推理接口(`/predict`、`/embed`、`/similarity`)鉴权。两处复用同一套 key 逻辑。

## 2. 范围

**做:**
- 通用 API Key 系统(创建/复制/吊销 + 校验),app-server 持有,单一事实源。
- model-server 推理接口接入 API Key 鉴权。
- badcase 上报 API(`X-Api-Key`)+ 四种任务类型(classification / ner / pair / embedding)的上报契约(“规则”,只读可查看)。
- Badcase 列表(按模型版本自动归类)+ 详情 + 按任务类型渲染的标注表单。
- 标注后的 badcase → 生成 `badcase-` 前缀训练集。
- “去修复”:复用现有训练流(支持把 badcase 集与原训练集多选合并)训练新版本。
- 新增权限与编号迁移;bootstrap 同步。

**不做(显式排除):**
- 阈值/置信度自动判定 badcase(业务只上报它认为坏的 case;平台不判断对错,只按模型版本归类)。
- 独立的 badcase 微服务(当前规模 YAGNI)。
- API Key 的细粒度配额/限流(后续 roadmap)。

## 3. 架构总览(方案 A)

badcase 作为 app-server 的一等实体,复用现有 dataset / training / RBAC 基础设施:

```
外部业务后端 ──X-Api-Key──> app-server  POST /badcase/report ──> badcases 表(按 model_version 归类)
                                            │
        前端 Badcase 页 <── JWT ──┤  列表/详情/标注/生成训练集
                                            │
        标注 badcase ──> build-dataset ──> Dataset(kind=train, name "badcase-…") + DatasetVersion
                                            │
        “去修复” ──> 现有训练流(可多选合并原训练集) ──> 新 ModelVersion

外部业务后端 ──X-Api-Key──> model-server /predict|/embed|/similarity
                                  └── 调 app-server 内部校验端点(带缓存)验证 key.scope=inference
```

**关键架构决策(请评审):** API Key 的存储与校验逻辑**只在 app-server**(单一事实源,DRY)。
- badcase 上报端点在 app-server,**进程内**直接查表校验。
- model-server 的推理接口需要 `X-Api-Key`,它通过调用 app-server 的内部校验端点 `POST /internal/api-keys/verify`(用现有 `X-Internal-Token` 保护)来验证,并带一个 60s 的内存 TTL 缓存,避免每次推理都打一次远程校验。这样 model-server 保持与存储解耦,且 key 逻辑不重复。
- 备选:让外部推理流量统一经 app-server 网关转发——会改变 API 详情里对外暴露的 URL(从 model-server 直连改为经 app-server),改动更大,故不采用;若评审更偏好网关式,可在此处切换。

## 4. 通用 API Key 系统

### 4.1 数据模型 `api_keys`(迁移 011)
| 列 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `name` | str | 人类可读名称(如 “客服系统-生产”) |
| `key_prefix` | str | 明文 key 的前 8 位,用于列表展示与定位(如 `mf_a1b2c3`) |
| `key_hash` | str | 完整明文 key 的 sha256,**库里只存 hash** |
| `scopes` | JSON | 字符串列表,取值 `inference` / `badcase:report`(一个 key 可多 scope) |
| `created_by` | int FK users | |
| `created_at` | datetime | |
| `last_used_at` | datetime null | 每次校验命中时异步更新(节流) |
| `revoked_at` | datetime null | 非空即吊销 |

- 明文 key 形如 `mf_<32位随机>`,**仅创建时在响应里返回一次**,之后不可再取(库里无明文)。
- 校验:取请求头 `X-Api-Key` → sha256 → 查 `key_hash` 且 `revoked_at IS NULL`,再校验所需 scope 在 `scopes` 内。

### 4.2 管理 API(JWT + `apikey:manage`)
- `GET /api-keys` — 列表(展示 name / key_prefix / scopes / 状态 / 创建者 / 时间;**不含明文/hash**)。
- `POST /api-keys` — `{name, scopes[]}` → 创建,**响应含一次性明文 key**。
- `DELETE /api-keys/{id}` — 吊销(置 `revoked_at`;软删,保留审计)。

### 4.3 内部校验端点(供 model-server 调用)
- `POST /internal/api-keys/verify`(`X-Internal-Token`):`{key, scope}` → `{valid: bool, key_id?, name?}`。命中即异步刷新 `last_used_at`。

### 4.4 model-server 接入
- 新增依赖:`require_api_key(scope="inference")`,从 `X-Api-Key` 读 key → 查内存缓存(TTL 60s)→ 未命中则调 app-server 内部校验端点 → 缓存结果。失败返回信封 `{code: 401, data: null, message: "invalid or missing api key"}`(保留 HTTP 401)。
- 加在 `/predict`、`/embed`、`/similarity` 上;`/load`、`/loaded`、`/health` 保持内部(`/load` 仅 app-server 调用,沿用现状)。
- model-server config 增加 `app_server_url`、`internal_token`(若已有则复用)。

## 5. Badcase 数据模型 `badcases`(迁移 012)
| 列 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `model_version_id` | int FK model_versions | 归类维度 |
| `task_type` | str | 冗余存(来自版本),便于查询/渲染 |
| `input` | JSON | 模型输入(按任务契约,见 §6) |
| `inference` | JSON | 模型推理输出(model-server 原样,见 §6) |
| `category` | str null | 派生分组键(如分类的预测标签),供页面次级归类 |
| `source` | str null | 来自哪个 api_key 的 name(上报来源) |
| `source_ref` | str null | 调用方自带 id,可选,用于去重 |
| `status` | str | `reported` → `annotated` → `used` |
| `annotation` | JSON null | 标注的正确答案(按任务契约) |
| `annotated_by` | int FK users null | |
| `annotated_at` | datetime null | |
| `dataset_version_id` | int FK dataset_versions null | 被纳入哪个 badcase 训练集 |
| `created_at` | datetime | 上报时间 |

- 去重:同一 `(source, source_ref)` 且 `source_ref` 非空时,重复上报返回已存在记录(幂等),不新建。
- `model_version_id` 必须存在,否则上报 422。

## 6. 上报契约(“规则”,每任务一套,只读可查看)

`GET /badcase/rules` 返回下表内容 + 示例 payload,供外部接入方与前端展示。契约即 `input` / `inference` / `annotation` 三段的字段形状,与 model-server 实际 I/O 对齐:

| 任务 | `input` | `inference`(model-server 原样回传) | `annotation`(系统内标注) | → 训练行 |
|---|---|---|---|---|
| classification | `{text}` | `{label, score}` | `{label}` | `{text, label}` |
| ner | `{tokens: [..]}` | `{tags: [..]}` | `{tags: [..]}` | `{tokens, tags}` |
| pair | `{text_a, text_b}` | `{score}` (0–1) | `{label}` ("0"/"1") | `{text_a, text_b, label}` |
| embedding | `{query, candidates: [text..]}` | `{ranked: [{text, score}..]}` | `{pos: [text..], neg: [text..]}` | `{query, pos, neg}` |

- 上报时校验:`input` 必含该任务必填字段;`inference` 尽量校验关键字段存在(缺失只告警不拒,以容忍调用方差异),非法 `input` 拒绝 422。
- embedding 标注:在详情页把 `candidates` 逐条标 pos/neg;`pos`/`neg` 取标注结果,未标的丢弃。

## 7. API 总表

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| `POST` | `/badcase/report` | **X-Api-Key**(scope `badcase:report`) | 上报一条 badcase |
| `GET` | `/badcase/rules` | JWT `badcase:read` | 查看四类上报契约 + 示例 |
| `GET` | `/badcases` | JWT `badcase:read` | 列表,支持 `model_version_id` / `status` / `category` 过滤 |
| `GET` | `/badcases/{id}` | JWT `badcase:read` | 详情 |
| `PATCH` | `/badcases/{id}/annotate` | JWT `badcase:annotate` | 提交标注;status→annotated |
| `POST` | `/badcases/build-dataset` | JWT `dataset:write` | `{badcase_ids[], name?}` → 建 `badcase-` 训练集 |
| `GET/POST/DELETE` | `/api-keys`、`/api-keys/{id}` | JWT `apikey:manage` | API Key 管理 |
| `POST` | `/internal/api-keys/verify` | X-Internal-Token | 供 model-server 校验 |

## 8. 标注 → 生成训练集

`build-dataset`:
1. 取选中 `badcase_ids`,要求都已 `annotated` 且**同一 task_type**(混类型拒绝 422)。
2. 把每条按 §6 的 “→ 训练行” 映射拼成 DataFrame。
3. 调用现有 `dataset_service` 落库:`Dataset(kind="train", task_type=该类型, name=强制 "badcase-" 前缀)` + 首个 `DatasetVersion`(parquet 快照)。
   - 默认名 `badcase-<模型名>-<yyyyMMddHHmmss>`,可传 `name`(无前缀则自动补 `badcase-`)。
4. 选中的 badcase 置 `status=used`,回填 `dataset_version_id`。
5. 返回新建的 dataset / version。

> 已 `used` 的 badcase 仍可被再次选入其它训练集(允许);默认列表用 `status` 过滤展示。

## 9. Badcase 修复

无需新后端:前端 “去修复” 跳到**现有训练抽屉**,预选刚生成的 `badcase-` 训练集(③ 训练集版本);用户可再多选原训练集**合并**(复用已实现的多数据集合并),选模型(默认 = badcase 所属模型,可改)提交,正常训出新版本。

## 10. RBAC 与鉴权

- 新增**用户权限**(进权限目录 + bootstrap `PERMISSION_CATALOG`/`SYSTEM_ROLES` + 迁移 013):`badcase:read`、`badcase:annotate`、`apikey:manage`。
- **API Key scope**(`inference` / `badcase:report`)是独立枚举,**不是** RBAC 用户权限,不进权限目录。
- 数据范围:`badcases` 含 `created_by`?——上报来自 api_key 无用户主体。**决策**:badcase 不按 `created_by` 做数据范围(上报无用户),`badcase:read` 即可见全部;标注与建集走对应权限。(若需团队隔离,后续可加 `project` 维度,本期不做。)
- 上报端点只认 `X-Api-Key`,不走 JWT。

## 11. 前端

- **新增菜单 / 页面:**
  - **Badcase**:按 模型 → 版本 自动分组(次级筛选 status / category / source);行展开或抽屉看 `input` + `inference`;按 task_type 渲染标注表单;多选已标注 → “生成 badcase 训练集” → “去修复”。
  - **上报规则**(只读):四类契约 + 示例 payload + 上报 curl(带 `X-Api-Key`),给接入方看。
  - **API Key**:列表(name/prefix/scopes/状态/创建者/时间)+ 新建(选 scopes,**一次性明文 key** 弹框复制)+ 吊销(ConfirmDialog)。
- **部署页 API 详情**(`apiDocs.ts`)更新:curl 示例加 `-H "X-Api-Key: <your key>"`,并说明需带 `inference` scope 的 key。
- 复用现有组件:Drawer / Cascade(多选)/ Toaster / ConfirmDialog / TableShell / loading。

## 12. 编号 SQL 迁移(铁律:改 models 必配迁移)
- `011_api_keys.sql` — 建 `api_keys` 表。
- `012_badcases.sql` — 建 `badcases` 表。
- `013_badcase_rbac.sql` — 权限目录加 `badcase:read`/`badcase:annotate`/`apikey:manage`,授予系统角色(超管 `*` 已含;admin 角色显式授予);`ON CONFLICT DO NOTHING` 幂等。`bootstrap.py` 同步。
- 全部幂等(`CREATE TABLE IF NOT EXISTS` / `INSERT … ON CONFLICT DO NOTHING`)。

## 13. 错误处理与边界
- 上报:未知/已删 `model_version_id` → 422;`input` 缺必填字段 → 422;`X-Api-Key` 缺失/无效/吊销/scope 不符 → 401。
- 推理(model-server):同上 401 用信封 `{code:401,data:null,message:…}`,保留 HTTP 401。
- 内部校验端点:缺 `X-Internal-Token` → 401;app-server 不可达时 model-server **拒绝**(fail-closed),返回 503 信封。
- build-dataset:含未标注 / 混 task_type → 422;空选择 → 422。
- embedding:`candidates` 为空或标注后 `pos` 为空 → 该条不可建集(校验提示)。
- api-key:明文仅返回一次;吊销后立即失效(校验查 `revoked_at`),model-server 缓存 60s 内可能仍放行(可接受;吊销说明里注明 ≤60s 生效)。

## 14. 测试
- API Key:创建返回一次性明文且库存 hash;校验命中/吊销失效;scope 不符拒绝;`apikey:manage` 鉴权。
- 内部校验端点:X-Internal-Token 保护;valid/invalid 分支。
- model-server:推理无 key→401、错 scope→401、有效→200(mock 校验端点 + 缓存命中只远程一次)。
- 上报:四类契约校验(合法入库 / 非法 422);未知版本 422;`(source,source_ref)` 幂等去重;按 model_version 归类。
- 标注:四类 annotate 写入 + status 流转。
- build-dataset:四类 badcase → 正确训练行;`badcase-` 前缀强制;混类型/未标注拒绝;status→used + 回填 version。
- 修复:复用训练流(已有多数据集合并测试覆盖)。

## 15. 分期(实现计划参考)
1. **通用 API Key 系统**(表 + 管理 API + 内部校验 + 前端 API Key 页)。
2. **model-server 推理鉴权**(接入 require_api_key + 缓存;部署 API 详情更新)。
3. **Badcase 上报 + 契约 + 列表归类**(report API + rules + badcases 表 + 列表/详情)。
4. **标注 + 生成训练集**(annotate + build-dataset,四类映射)。
5. **修复联动 + RBAC + 收尾**(去修复跳转、权限/迁移、规则页、测试补全)。

## 16. 待评审的开放决策
1. 推理鉴权落点:**model-server 调 app-server 内部校验 + 缓存**(本稿默认)vs **app-server 网关转发**。
2. embedding 上报契约里 `candidates` 是否必须带相似度(`ranked`),还是允许只给候选文本(平台不需要分数也能标注)?本稿设为 `ranked` 可选、纯候选文本即可标注。
3. badcase 是否需要 `created_by` / 数据范围隔离?本稿设为不隔离(上报无用户主体)。
