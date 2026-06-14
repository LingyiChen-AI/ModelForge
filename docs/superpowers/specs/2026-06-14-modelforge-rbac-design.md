# ModelForge RBAC 设计文档

- 日期:2026-06-14
- 状态:已评审,待实现计划
- 范围:app-server 的认证(JWT 登录)、自定义角色 RBAC、角色级数据范围、超管的用户/角色管理、引导初始化与护栏、前端登录与管理页

## 1. 背景与目标

当前 `users` 表仅 `id/name/email/role(str)`,**无任何认证与鉴权**(所有端点只依赖 DB 会话;`created_by` 存在但从未写入)。本设计补齐:

- **认证**:自建 JWT 登录(email+密码)。
- **授权**:完整自定义角色 RBAC —— 超管在**固定权限目录**上自由组合出自定义角色。
- **数据范围**:挂在**角色**上(`all` / `own`);超管只维护角色即可。
- **治理范围**:全部业务资源(数据集/版本、训练、模型版本、评估、部署)。
- **超管能力**:管理其他用户(角色、启停、改密)与角色(权限集、数据范围)。

### 关键决策

1. 认证 = 自建 JWT(HS256),`get_current_user` 依赖。
2. 权限码 = **固定枚举目录**(对应代码里的真实鉴权点);角色可自定义,权限码不可凭空新增。
3. `users.role:str` → `role_id` FK(破坏式改造;当前无真实用户,仅 seed)。
4. **`data_scope` 放在 `roles` 上**(非用户);用户从角色继承。
5. 鉴权落到**每接口依赖** `require("code")`;数据范围用 `created_by` 列 + `apply_scope()` 查询助手(行级)。
6. 内部回调端点用静态 `X-Internal-Token` 护栏;worker 带上。

### 非目标(YAGNI)

- 不做 OAuth/SSO/刷新令牌轮换(单团队,短期 access token 足够;过期重登)。
- 不做按资源逐条 ACL(own/all 足够)。
- train-worker / model-server 不接用户态(内部组件)。

## 2. 权限目录(固定枚举)

| code | 含义 | 挂载端点(示例) |
|---|---|---|
| `dataset:read` | 看数据集/版本 | GET /datasets, GET /datasets/{id}/versions |
| `dataset:write` | 建数据集/传版本 | POST /datasets, POST /datasets/{id}/versions |
| `training:read` | 看训练任务 | GET /training-jobs(/{id}) |
| `training:run` | 发起训练 | POST /training-jobs |
| `model:read` | 看模型版本 | GET /model-versions |
| `eval:read` | 看评估 | GET /eval-runs(/{id}) |
| `eval:run` | 发起评估 | POST /eval-runs |
| `deploy:read` | 看部署 | GET /deployments |
| `deploy:write` | 部署/停止 | POST /deployments, POST /deployments/{id}/stop |
| `user:manage` | 用户管理 | /users* |
| `role:manage` | 角色管理 | /roles*, GET /permissions |
| `*` | 通配(全允) | 仅系统 superadmin 角色 |

> `model-versions` 由训练回调产生,无独立"写"端点;`model:read` 即可。后续若加 promote 端点再扩 `model:promote`。

## 3. 数据模型(PostgreSQL)

```
roles
  id PK, name(unique), description,
  data_scope: 'all' | 'own' (默认 'own'),
  is_system: bool (默认 false),
  created_at, updated_at

permissions
  id PK, code(unique), description        # 启动时按权限目录幂等 seed

role_permissions
  role_id FK->roles.id, permission_id FK->permissions.id,
  UNIQUE(role_id, permission_id)

users  (改造)
  id PK, name, email(unique),
  password_hash: str,
  role_id: FK->roles.id (nullable),
  is_active: bool (默认 true),
  created_at, updated_at
  # 删除旧的 role:str 列
```

各业务资源加 `created_by: int|None FK->users.id`:
- `Dataset`(已有)、`TrainingJob`、`ModelVersion`、`EvalRun`、`Deployment`。
- 创建时 `created_by = current_user.id`。
- **`ModelVersion`** 由 worker 回调创建(无用户上下文)→ 取来源 `TrainingJob.created_by` 继承(在 `upsert_model_version_from_result` 里赋值)。

### seed 角色(超管可改非系统角色)

| 角色 | data_scope | 权限 | is_system |
|---|---|---|---|
| `superadmin` | all | `*` | true(不可删/改) |
| `admin` | all | 全部业务读写 + `user:manage` 之外 | false |
| `member` | own | 读 + `*:run`/`*:write`(业务) | false |
| `viewer` | own | 仅各 `*:read` | false |

> admin 默认不含 `user:manage`/`role:manage`(仅 superadmin 管人管角色);如需可由超管在角色管理里加。

## 4. 认证流(JWT)

依赖:`pyjwt`、`passlib[bcrypt]`。`app/config.py` 增:`jwt_secret: str`、`jwt_algorithm: str = "HS256"`、`jwt_expire_minutes: int = 720`、`internal_token: str = "modelforge-internal"`、`seed_admin_email`、`seed_admin_password`。

- `POST /auth/login {email, password}`:查 user(active)→ bcrypt 校验 → 签发 `{sub: user_id, exp}` HS256 → 返回:
  ```json
  {"access_token":"...","token_type":"bearer",
   "user":{"id":1,"name":"...","email":"...","role":"superadmin",
           "data_scope":"all","permissions":["*"]}}
  ```
- `GET /auth/me`(需登录):返回当前用户 + 角色 + data_scope + 权限码集(前端显隐用)。
- `app/auth.py`:
  - `hash_password` / `verify_password`(passlib CryptContext bcrypt)。
  - `create_access_token(user_id)` / `decode_token`。
  - `get_current_user(authorization: Header)` 依赖:解析 Bearer → decode → 载入 user → `is_active` → 返回 ORM user;失败 **401**。
  - `permission_codes(user)`:聚合 `user.role.permissions` 的 code 集(无角色→空集)。

## 5. 鉴权 + 数据范围执行

`app/authz.py`:
- `has_permission(user, code) -> bool`:`"*" in codes or code in codes`。
- `require(code)`:依赖工厂,内部 `Depends(get_current_user)`,无权限 **403 "permission denied: {code}"**;返回 user 供路由复用。
- `effective_scope(user) -> str`:`user.role.data_scope`(无角色按 `own`);若用户权限含 `*` 视为 `all`。
- `apply_scope(stmt, Model, user)`:`effective_scope(user)=='own'` → `stmt.where(Model.created_by == user.id)`;`all` 原样。
- 单条访问:own 用户取/改非自己 `created_by` 的资源 → **404**(不泄露存在性)。

各路由改造(示例):
```python
@router.post("", status_code=201)
def create_dataset(body, user=Depends(require("dataset:write")), db=Depends(get_db)):
    ds = Dataset(..., created_by=user.id); ...

@router.get("")
def list_datasets(user=Depends(require("dataset:read")), db=Depends(get_db)):
    return db.execute(apply_scope(select(Dataset), Dataset, user)).scalars().all()
```
覆盖 datasets / training / models / eval / deployments 全部读写端点(治理映射见第 2 节)。

## 6. 超管管理 API

**用户**(`require("user:manage")`):
- `POST /users {name,email,password,role_id}` → 建用户(bcrypt 存)
- `GET /users` / `GET /users/{id}`
- `PATCH /users/{id} {role_id?, is_active?}`
- `POST /users/{id}/reset-password {password}`

**角色**(`require("role:manage")`):
- `GET /permissions` → 权限目录
- `GET /roles` / `GET /roles/{id}`
- `POST /roles {name, description, data_scope, permission_codes:[]}`
- `PATCH /roles/{id} {description?, data_scope?, permission_codes?}` — `is_system` 角色拒改(400)
- `DELETE /roles/{id}` — `is_system` 拒删(400);被用户引用时拒删(409,提示先改派)

`app/services/user_service.py` / `role_service.py` 承载逻辑;API 薄。

## 7. 引导初始化 + 安全护栏

- `app/bootstrap.py` `seed()`(幂等):
  1. 按权限目录 upsert `permissions`。
  2. upsert 四个系统/默认角色及其 `role_permissions`(superadmin=`*`)。
  3. 若无 superadmin 用户 → 用 `seed_admin_email`/`seed_admin_password` 建一个(角色=superadmin)。
  - 在 app 启动事件调用,或独立 `python -m app.bootstrap` 脚本;迁移负责建表,seed 负责数据。
- 护栏(service 层):
  - superadmin 角色 `is_system` 不可删/改。
  - 不可停用 / 不可改派**最后一个**在职 superadmin 用户(`is_active` 且角色 superadmin 的计数==1 时拒绝)→ 422。

## 8. 内部端点护栏

- `POST /training-jobs/internal/{job_id}/result` 增依赖 `require_internal_token`:校验 `X-Internal-Token == settings.internal_token`,否则 **401**。
- train-worker:`worker/config.py` 增 `internal_token`,`report_result` 的 POST 带 `headers={"X-Internal-Token": settings.internal_token}`。
- 默认值两边一致(`"modelforge-internal"`),生产用 env 覆盖。

## 9. 前端

- `src/auth.ts`:登录、登出、读/存 JWT(localStorage)、当前用户与权限集;axios 拦截器附 `Authorization`,响应 401 → 清 token 跳登录。
- `LoginPage.tsx`:email/密码登录。
- `AuthContext`:`user` + `can(code)`;未登录只显示登录页。
- 导航/按钮按 `can(code)` 显隐(如无 `dataset:write` 隐藏"新建")。
- 管理页(仅对应权限可见):
  - `UsersPage.tsx`:列表 / 建用户 / 改角色·启停 / 重置密码。
  - `RolesPage.tsx`:列表 / 建角色(选权限码 + data_scope)/ 改 / 删;展示权限目录。

## 10. 测试策略

- 单元:`hash/verify_password`、`create/decode_token`(含过期)、`has_permission`(通配/子集)、`effective_scope`、`apply_scope`(own 加过滤、all 不加)。
- 接口(SQLite + 注入测试用户):
  - 登录成功/密码错(401)/停用用户(401)。
  - 受保护端点:无 token 401、有 token 无权限 403、有权限 200。
  - 数据范围:own 用户列表只见自己 `created_by`、取他人资源 404;all 用户全见。
  - 用户管理需 `user:manage`;角色管理需 `role:manage`;系统角色拒改/删;最后一个 superadmin 护栏 422。
  - 内部回调:缺/错 `X-Internal-Token` 401,正确 201。
  - seed 幂等(跑两次结果一致)。

## 11. 实现分阶段建议(供拆 plan)

1. **认证地基**:依赖、config、roles/permissions/role_permissions 表、users 改造(role_id/password_hash/is_active)+ 迁移;auth.py(hash/jwt/get_current_user);bootstrap seed;`/auth/login` `/auth/me`。
2. **鉴权与数据范围**:authz.py(require/apply_scope);各业务资源加 `created_by` + 迁移;给 datasets/training/models/eval/deployments 端点挂 `require` 与 scope;ModelVersion 继承 created_by;内部 token 护栏 + worker 接线。
3. **超管管理 API**:user_service/role_service + /users /roles /permissions + 护栏。
4. **前端**:auth + 登录页 + 守卫 + 用户/角色管理页 + 按权限显隐。

## 12. 风险/影响

- users 改造是破坏式:旧 `role:str` 删除,需迁移 + seed;现无真实数据,影响可控。
- 给所有读端点加 `require(...read)` 会让未登录调用从"可访问"变 401 —— 这是预期(现在是全开放)。
- ModelVersion 的 created_by 依赖来源训练任务 created_by;历史(本设计前)产生的 ModelVersion created_by 为空 → own 用户看不到,可接受(或迁移时回填)。
