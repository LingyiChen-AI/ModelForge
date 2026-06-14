# ModelForge RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 app-server 加上 JWT 认证、自定义角色 RBAC、角色级数据范围(all/own)、超管的用户/角色管理,并把全部业务端点纳入鉴权与数据范围过滤。

**Architecture:** 仅 app-server 做策略点。`roles`/`permissions`/`role_permissions` 三表 + `users` 改造(role_id/password_hash/is_active);权限码是固定目录,角色可自定义。鉴权用每接口 `Depends(require(code))`,数据范围用各资源 `created_by` 列 + `apply_scope()` 查询助手。内部回调用静态 `X-Internal-Token`。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、`pyjwt`、`bcrypt`、pytest、React+TS。

参考 spec:`docs/superpowers/specs/2026-06-14-modelforge-rbac-design.md`。

---

## 文件结构

```
services/app-server/app/
  config.py                      # 增 jwt_*/internal_token/seed_admin_*
  models/rbac.py                 # Role / Permission / RolePermission(新)
  models/user.py                 # 改造:password_hash/role_id/is_active,去掉 role:str
  models/{dataset,training}.py   # 各资源加 created_by(dataset 已有)
  auth.py                        # 密码哈希、JWT、get_current_user、require_internal_token
  authz.py                       # has_permission/require/effective_scope/apply_scope
  bootstrap.py                   # seed 权限目录 + 系统角色 + 初始超管
  schemas/auth.py rbac.py        # 登录/用户/角色 I/O
  services/user_service.py role_service.py
  api/auth.py users.py roles.py  # 路由
  api/{datasets,training,eval,models,deployment}.py  # 挂 require + scope
  main.py                        # 注册新路由
  alembic/versions/*             # rbac 表迁移 + created_by 迁移
  tests/conftest.py              # 增 session_factory / make_user / auth_headers 助手
frontend/src/
  auth.ts                        # 登录/登出/token/can()
  context/AuthContext.tsx
  pages/LoginPage.tsx UsersPage.tsx RolesPage.tsx
  api/client.ts App.tsx          # 拦截器 + 路由守卫 + 按权限显隐
services/train-worker/worker/
  config.py tasks.py             # internal_token + 回调带 header
```

---

# 阶段 1:认证地基

### Task 1: config + RBAC 模型 + users 改造 + 迁移

**Files:**
- Modify: `services/app-server/app/config.py`
- Create: `services/app-server/app/models/rbac.py`
- Modify: `services/app-server/app/models/user.py`
- Modify: `services/app-server/app/models/__init__.py`
- Test: `services/app-server/tests/test_rbac_models.py`

- [ ] **Step 1: 写失败测试**
```python
# services/app-server/tests/test_rbac_models.py
from app.models.base import Base
import app.models  # noqa

def test_rbac_tables_and_user_columns():
    t = Base.metadata.tables
    assert {"roles", "permissions", "role_permissions"} <= set(t)
    rcols = t["roles"].columns.keys()
    assert {"id","name","description","data_scope","is_system"} <= set(rcols)
    ucols = t["users"].columns.keys()
    assert {"password_hash","role_id","is_active"} <= set(ucols)
    assert "role" not in ucols  # 旧字符串列已移除
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_rbac_models.py -q`
Expected: FAIL — KeyError: 'roles'

- [ ] **Step 3: 实现 config 增项**
在 `app/config.py` 的 `Settings` 增字段:
```python
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    internal_token: str = "modelforge-internal"
    seed_admin_email: str = "admin@modelforge.local"
    seed_admin_password: str = "admin12345"
```

- [ ] **Step 4: 实现 rbac 模型**
```python
# services/app-server/app/models/rbac.py
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str] = mapped_column(default="")

class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"), primary_key=True)

class Role(Base, TimestampMixin):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str] = mapped_column(default="")
    data_scope: Mapped[str] = mapped_column(default="own")   # 'all' | 'own'
    is_system: Mapped[bool] = mapped_column(default=False)
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", lazy="selectin")
```

- [ ] **Step 5: 改造 user 模型**
```python
# services/app-server/app/models/user.py  (整体替换)
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str] = mapped_column(default="")
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    role: Mapped["Role | None"] = relationship(lazy="selectin")
```
更新 `app/models/__init__.py`,导入并导出 `Role, Permission, RolePermission`(从 `app.models.rbac`),保持已有导出:
```python
from app.models.rbac import Role, Permission, RolePermission
# 加进 __all__: "Role","Permission","RolePermission"
```
（确保 `import app.models.rbac` 在 `__init__` 里发生,使表注册到 Base.metadata。）

- [ ] **Step 6: 运行确认通过 + 迁移**

Run:
```bash
cd services/app-server && python -m pytest tests/test_rbac_models.py -q   # PASS
alembic revision --autogenerate -m "rbac tables and user auth columns" && alembic upgrade head
```
Expected: 迁移新增 roles/permissions/role_permissions,并对 users 增 password_hash/role_id/is_active、删除 role 列(`include_object` 过滤已忽略 MLflow 表)。用 python inspect 确认。

> 注:autogenerate 会对 users 生成 `op.drop_column('role')` 与 add_column;若 SQLite/PG 对 drop_column 有限制,PG 16 支持直接 drop。确认迁移 upgrade()/downgrade() 合理(downgrade 加回 role 列、删新列与新表)。

- [ ] **Step 7: 提交**
```bash
git add services/app-server/app/config.py services/app-server/app/models services/app-server/alembic/versions services/app-server/tests/test_rbac_models.py
git commit -m "feat(app-server): RBAC tables and user auth columns"
```

---

### Task 2: auth.py(密码/JWT/当前用户)+ 测试助手

**Files:**
- Modify: `services/app-server/pyproject.toml`(加 `pyjwt`, `bcrypt`)
- Create: `services/app-server/app/auth.py`
- Modify: `services/app-server/tests/conftest.py`(增助手)
- Test: `services/app-server/tests/test_auth.py`

- [ ] **Step 1: 装依赖** `pip install pyjwt bcrypt`,并在 app-server pyproject dependencies 加 `"pyjwt>=2.8"`, `"bcrypt>=4.0"`。

- [ ] **Step 2: 写失败测试**
```python
# services/app-server/tests/test_auth.py
import pytest
from app.auth import hash_password, verify_password, create_access_token, decode_token

def test_password_roundtrip():
    h = hash_password("secret")
    assert h != "secret"
    assert verify_password("secret", h)
    assert not verify_password("wrong", h)

def test_jwt_roundtrip():
    tok = create_access_token(42)
    assert decode_token(tok)["sub"] == "42"

def test_jwt_invalid():
    import jwt
    with pytest.raises(Exception):
        decode_token("not-a-token")
```

- [ ] **Step 3: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_auth.py -q`
Expected: FAIL — ModuleNotFoundError: app.auth

- [ ] **Step 4: 实现 auth.py**
```python
# services/app-server/app/auth.py
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.user import User

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode(), password_hash.encode())

def create_access_token(user_id: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    payload = {"sub": str(user_id),
               "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

def get_current_user(authorization: str | None = Header(default=None),
                     db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        payload = decode_token(authorization.split(" ", 1)[1])
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(401, "invalid token")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "inactive or unknown user")
    return user

def permission_codes(user: User) -> set[str]:
    if not user.role:
        return set()
    return {p.code for p in user.role.permissions}

def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    if x_internal_token != settings.internal_token:
        raise HTTPException(401, "invalid internal token")
```

- [ ] **Step 5: 运行确认通过** `python -m pytest tests/test_auth.py -q` → PASS。

- [ ] **Step 6: 增测试助手(append 到现有 conftest.py)**
现有 `tests/conftest.py` 已有 s3 端点修补;在其末尾追加:
```python
# --- RBAC 测试助手 ---
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def session_factory(tmp_path):
    from app.models import Base
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(eng)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    return dbmod.SessionLocal

def make_user(db, *, codes=("*",), data_scope="all", email="u@x.com",
              name="u", active=True):
    from app.models.rbac import Role, Permission
    from app.models.user import User
    perms = [Permission(code=c, description=c) for c in codes]
    for p in perms:
        db.add(p)
    role = Role(name=f"role-{email}", data_scope=data_scope, permissions=perms)
    db.add(role); db.commit()
    u = User(name=name, email=email, role_id=role.id, is_active=active)
    db.add(u); db.commit(); db.refresh(u)
    return u

def auth_headers(user_id):
    from app.auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}
```

- [ ] **Step 7: 提交**
```bash
git add services/app-server/pyproject.toml services/app-server/app/auth.py services/app-server/tests/conftest.py services/app-server/tests/test_auth.py
git commit -m "feat(app-server): password hashing, JWT and get_current_user"
```

---

### Task 3: bootstrap seed(权限目录 + 系统角色 + 初始超管)

**Files:**
- Create: `services/app-server/app/bootstrap.py`
- Test: `services/app-server/tests/test_bootstrap.py`

- [ ] **Step 1: 写失败测试**
```python
# services/app-server/tests/test_bootstrap.py
from tests.conftest import make_user  # noqa (确保 conftest 可导入)

def test_seed_idempotent(session_factory):
    from app.bootstrap import seed
    from app.models.rbac import Role, Permission
    from app.models.user import User
    from sqlalchemy import select, func
    S = session_factory
    db = S()
    seed(db); seed(db)  # 跑两次
    assert db.execute(select(func.count()).select_from(Permission)).scalar() == 12
    roles = {r.name: r for r in db.execute(select(Role)).scalars()}
    assert set(roles) == {"superadmin", "admin", "member", "viewer"}
    assert roles["superadmin"].is_system is True
    assert {p.code for p in roles["superadmin"].permissions} == {"*"}
    assert roles["member"].data_scope == "own"
    # 初始超管唯一
    admins = db.execute(select(User).where(User.role_id == roles["superadmin"].id)).scalars().all()
    assert len(admins) == 1 and admins[0].is_active
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_bootstrap.py -q`
Expected: FAIL — ModuleNotFoundError: app.bootstrap

- [ ] **Step 3: 实现 bootstrap.py**
```python
# services/app-server/app/bootstrap.py
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.rbac import Role, Permission
from app.models.user import User
from app.auth import hash_password

PERMISSION_CATALOG = [
    ("dataset:read", "看数据集/版本"), ("dataset:write", "建数据集/传版本"),
    ("training:read", "看训练任务"), ("training:run", "发起训练"),
    ("model:read", "看模型版本"),
    ("eval:read", "看评估"), ("eval:run", "发起评估"),
    ("deploy:read", "看部署"), ("deploy:write", "部署/停止"),
    ("user:manage", "用户管理"), ("role:manage", "角色管理"),
    ("*", "通配"),
]
READS = ["dataset:read", "training:read", "model:read", "eval:read", "deploy:read"]
BUSINESS = READS + ["dataset:write", "training:run", "eval:run", "deploy:write"]
SYSTEM_ROLES = [
    ("superadmin", "超级管理员", "all", True, ["*"]),
    ("admin", "管理员", "all", False, BUSINESS),
    ("member", "成员", "own", False, BUSINESS),
    ("viewer", "只读", "own", False, READS),
]

def seed(db: Session) -> None:
    by_code = {}
    for code, desc in PERMISSION_CATALOG:
        p = db.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
        if not p:
            p = Permission(code=code, description=desc); db.add(p)
        by_code[code] = p
    db.flush()
    for name, desc, scope, is_sys, codes in SYSTEM_ROLES:
        r = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
        if not r:
            r = Role(name=name, description=desc, data_scope=scope, is_system=is_sys)
            db.add(r); db.flush()
        r.permissions = [by_code[c] for c in codes]
    db.flush()
    superadmin = db.execute(select(Role).where(Role.name == "superadmin")).scalar_one()
    has_admin = db.execute(
        select(User).where(User.role_id == superadmin.id)).first()
    if not has_admin:
        db.add(User(name="admin", email=settings.seed_admin_email,
                    password_hash=hash_password(settings.seed_admin_password),
                    role_id=superadmin.id, is_active=True))
    db.commit()

def run() -> None:
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()

if __name__ == "__main__":
    run()
```

- [ ] **Step 4: 运行确认通过** `python -m pytest tests/test_bootstrap.py -q` → PASS。

- [ ] **Step 5: 提交**
```bash
git add services/app-server/app/bootstrap.py services/app-server/tests/test_bootstrap.py
git commit -m "feat(app-server): bootstrap seed for permissions, roles and admin"
```

---

### Task 4: /auth/login + /auth/me

**Files:**
- Create: `services/app-server/app/schemas/auth.py`
- Create: `services/app-server/app/api/auth.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_auth_api.py`

- [ ] **Step 1: 写失败测试**
```python
# services/app-server/tests/test_auth_api.py
from fastapi.testclient import TestClient
from tests.conftest import make_user, auth_headers

def test_login_and_me(session_factory):
    S = session_factory
    db = S()
    from app.auth import hash_password
    u = make_user(db, codes=("dataset:read", "dataset:write"), data_scope="own",
                  email="a@x.com")
    u.password_hash = hash_password("pw"); db.add(u); db.commit()
    uid = u.id; db.close()

    from app.main import app
    c = TestClient(app)
    r = c.post("/auth/login", json={"email": "a@x.com", "password": "pw"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert set(body["user"]["permissions"]) == {"dataset:read", "dataset:write"}
    assert body["user"]["data_scope"] == "own"

    r = c.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert r.status_code == 200 and r.json()["email"] == "a@x.com"

    assert c.post("/auth/login", json={"email": "a@x.com", "password": "bad"}).status_code == 401
    assert c.get("/auth/me").status_code == 401  # 无 token
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_auth_api.py -q`
Expected: FAIL — 404

- [ ] **Step 3: 实现 schema + 路由**
```python
# services/app-server/app/schemas/auth.py
from pydantic import BaseModel

class LoginRequest(BaseModel):
    email: str
    password: str

class UserInfo(BaseModel):
    id: int
    name: str
    email: str
    role: str | None
    data_scope: str
    permissions: list[str]

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
```
```python
# services/app-server/app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.user import User
from app.auth import (verify_password, create_access_token, get_current_user,
                      permission_codes)
from app.schemas.auth import LoginRequest, LoginResponse, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])

def _user_info(user: User) -> UserInfo:
    return UserInfo(id=user.id, name=user.name, email=user.email,
                    role=user.role.name if user.role else None,
                    data_scope=user.role.data_scope if user.role else "own",
                    permissions=sorted(permission_codes(user)))

@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    return LoginResponse(access_token=create_access_token(user.id), user=_user_info(user))

@router.get("/me", response_model=UserInfo)
def me(user: User = Depends(get_current_user)):
    return _user_info(user)
```
`app/main.py` 追加:`from app.api import auth` + `app.include_router(auth.router)`。

- [ ] **Step 4: 运行确认通过** `python -m pytest tests/test_auth_api.py -q` → PASS;全套 `python -m pytest -q` 仍绿(此时尚未给业务端点加鉴权)。

- [ ] **Step 5: 提交**
```bash
git add services/app-server/app/schemas/auth.py services/app-server/app/api/auth.py services/app-server/app/main.py services/app-server/tests/test_auth_api.py
git commit -m "feat(app-server): /auth/login and /auth/me"
```

---

# 阶段 2:鉴权与数据范围

### Task 5: authz.py(require / apply_scope)

**Files:**
- Create: `services/app-server/app/authz.py`
- Test: `services/app-server/tests/test_authz.py`

- [ ] **Step 1: 写失败测试**
```python
# services/app-server/tests/test_authz.py
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from tests.conftest import make_user, auth_headers

def test_has_permission_and_scope(session_factory):
    from app.authz import has_permission, effective_scope
    S = session_factory; db = S()
    admin = make_user(db, codes=("*",), data_scope="all", email="ad@x.com")
    member = make_user(db, codes=("dataset:read",), data_scope="own", email="mb@x.com")
    assert has_permission(admin, "anything:at:all")  # 通配
    assert has_permission(member, "dataset:read")
    assert not has_permission(member, "dataset:write")
    assert effective_scope(admin) == "all"   # 通配视为 all
    assert effective_scope(member) == "own"

def test_require_dependency(session_factory):
    from app.authz import require
    S = session_factory; db = S()
    member = make_user(db, codes=("dataset:read",), email="m@x.com", data_scope="own")
    mid = member.id; db.close()
    app = FastAPI()
    @app.get("/x")
    def x(u=Depends(require("dataset:write"))):
        return {"ok": True}
    c = TestClient(app)
    assert c.get("/x").status_code == 401                       # 无 token
    assert c.get("/x", headers=auth_headers(mid)).status_code == 403  # 有 token 无权限
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_authz.py -q`
Expected: FAIL — ModuleNotFoundError: app.authz

- [ ] **Step 3: 实现 authz.py**
```python
# services/app-server/app/authz.py
from fastapi import Depends, HTTPException
from app.auth import get_current_user, permission_codes
from app.models.user import User

def has_permission(user: User, code: str) -> bool:
    codes = permission_codes(user)
    return "*" in codes or code in codes

def require(code: str):
    def dep(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, code):
            raise HTTPException(403, f"permission denied: {code}")
        return user
    return dep

def effective_scope(user: User) -> str:
    if "*" in permission_codes(user):
        return "all"
    return user.role.data_scope if user.role else "own"

def apply_scope(stmt, model, user: User):
    if effective_scope(user) == "own":
        return stmt.where(model.created_by == user.id)
    return stmt
```

- [ ] **Step 4: 运行确认通过** `python -m pytest tests/test_authz.py -q` → PASS。

- [ ] **Step 5: 提交**
```bash
git add services/app-server/app/authz.py services/app-server/tests/test_authz.py
git commit -m "feat(app-server): authz require() and data-scope helpers"
```

---

### Task 6: 各业务资源加 created_by + 迁移

**Files:**
- Modify: `services/app-server/app/models/training.py`(TrainingJob/ModelVersion/EvalRun/Deployment 加 created_by)
- Test: `services/app-server/tests/test_created_by_columns.py`

- [ ] **Step 1: 写失败测试**
```python
# services/app-server/tests/test_created_by_columns.py
from app.models.base import Base
import app.models  # noqa

def test_created_by_present():
    t = Base.metadata.tables
    for tbl in ("training_jobs", "model_versions", "eval_runs", "deployments"):
        assert "created_by" in t[tbl].columns.keys()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_created_by_columns.py -q`
Expected: FAIL — AssertionError

- [ ] **Step 3: 实现** —— 在 `app/models/training.py` 的 TrainingJob / ModelVersion / EvalRun / Deployment 四个类各加一行(复用已 import 的 ForeignKey/Mapped/mapped_column):
```python
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
```

- [ ] **Step 4: 运行确认通过 + 迁移**

Run:
```bash
cd services/app-server && python -m pytest tests/test_created_by_columns.py -q   # PASS
alembic revision --autogenerate -m "add created_by to business resources" && alembic upgrade head
```
确认迁移仅对 training_jobs/model_versions/eval_runs/deployments 各 add_column created_by(FK users.id)。python inspect 确认。

- [ ] **Step 5: 提交**
```bash
git add services/app-server/app/models/training.py services/app-server/alembic/versions services/app-server/tests/test_created_by_columns.py
git commit -m "feat(app-server): add created_by to training/model/eval/deployment"
```

---

### Task 7: datasets 端点挂鉴权 + 数据范围(并更新既有测试)

**Files:**
- Modify: `services/app-server/app/api/datasets.py`
- Modify: `services/app-server/tests/test_datasets_api.py`
- Test: `services/app-server/tests/test_datasets_authz.py`

- [ ] **Step 1: 写数据范围测试(新)**
```python
# services/app-server/tests/test_datasets_authz.py
import io, pandas as pd, boto3
from moto import mock_aws
from fastapi.testclient import TestClient
from tests.conftest import make_user, auth_headers

@mock_aws
def test_own_scope_isolation(session_factory):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="datasets")
    S = session_factory; db = S()
    a = make_user(db, codes=("dataset:read","dataset:write"), data_scope="own", email="a@x.com")
    b = make_user(db, codes=("dataset:read","dataset:write"), data_scope="own", email="b@x.com")
    aid, bid = a.id, b.id; db.close()

    from app.main import app
    c = TestClient(app)
    r = c.post("/datasets", json={"name":"da","kind":"train","task_type":"classification"},
               headers=auth_headers(aid))
    assert r.status_code == 201
    ds_a = r.json()["id"]
    # b 看不到 a 的数据集
    assert c.get("/datasets", headers=auth_headers(bid)).json() == []
    # a 能看到自己的
    assert len(c.get("/datasets", headers=auth_headers(aid)).json()) == 1
    # b 取 a 的版本列表 → 404(own 范围)
    assert c.get(f"/datasets/{ds_a}/versions", headers=auth_headers(bid)).status_code == 404

@mock_aws
def test_requires_permission(session_factory):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="datasets")
    S = session_factory; db = S()
    viewer = make_user(db, codes=("dataset:read",), data_scope="own", email="v@x.com")
    vid = viewer.id; db.close()
    from app.main import app
    c = TestClient(app)
    assert c.post("/datasets", json={"name":"x","kind":"train","task_type":"classification"},
                  headers=auth_headers(vid)).status_code == 403   # 无 dataset:write
    assert c.get("/datasets").status_code == 401                  # 无 token
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_datasets_authz.py -q`
Expected: FAIL — 当前无鉴权,返回 201/200 而非 403/401/404

- [ ] **Step 3: 改造 datasets.py(整体替换)**
```python
# services/app-server/app/api/datasets.py
import io, pandas as pd
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require, apply_scope
from app.storage import build_storage
from app.models.user import User
from app.models.dataset import Dataset, DatasetVersion
from app.schemas.dataset import DatasetCreate, DatasetOut, DatasetVersionOut
from app.services.dataset_service import create_version

router = APIRouter(prefix="/datasets", tags=["datasets"])

def _get_owned_dataset(db: Session, dataset_id: int, user: User) -> Dataset:
    stmt = apply_scope(select(Dataset).where(Dataset.id == dataset_id), Dataset, user)
    ds = db.execute(stmt).scalar_one_or_none()
    if not ds:
        raise HTTPException(404, "dataset not found")
    return ds

@router.post("", response_model=DatasetOut, status_code=201)
def create_dataset(body: DatasetCreate, user: User = Depends(require("dataset:write")),
                   db: Session = Depends(get_db)):
    ds = Dataset(name=body.name, kind=body.kind.value, task_type=body.task_type.value,
                 created_by=user.id)
    db.add(ds); db.commit(); db.refresh(ds)
    return ds

@router.get("", response_model=list[DatasetOut])
def list_datasets(user: User = Depends(require("dataset:read")), db: Session = Depends(get_db)):
    return db.execute(apply_scope(select(Dataset), Dataset, user)).scalars().all()

def _read_upload(file: UploadFile) -> pd.DataFrame:
    raw = file.file.read()
    if file.filename.endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw))
    if file.filename.endswith(".jsonl"):
        return pd.read_json(io.BytesIO(raw), lines=True)
    raise HTTPException(400, "only .csv or .jsonl supported")

@router.post("/{dataset_id}/versions", response_model=DatasetVersionOut, status_code=201)
def upload_version(dataset_id: int, file: UploadFile = File(...), note: str = Form(""),
                   user: User = Depends(require("dataset:write")), db: Session = Depends(get_db)):
    ds = _get_owned_dataset(db, dataset_id, user)
    df = _read_upload(file)
    try:
        return create_version(db, build_storage(), ds, df, note)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("/{dataset_id}/versions", response_model=list[DatasetVersionOut])
def list_versions(dataset_id: int, user: User = Depends(require("dataset:read")),
                  db: Session = Depends(get_db)):
    _get_owned_dataset(db, dataset_id, user)   # own 范围校验,非属主 404
    return db.execute(select(DatasetVersion)
                      .where(DatasetVersion.dataset_id == dataset_id)
                      .order_by(DatasetVersion.version_no.desc())).scalars().all()
```

- [ ] **Step 4: 更新既有 test_datasets_api.py(让它带 token)**
把 `tests/test_datasets_api.py` 的 `test_dataset_create_upload_list` 改为创建一个全权用户并带 header(其余断言不变)。在创建 client 后、首个请求前加:
```python
    from tests.conftest import make_user, auth_headers
    db2 = dbmod.SessionLocal()
    admin = make_user(db2, codes=("*",), data_scope="all", email="root@x.com")
    h = auth_headers(admin.id); db2.close()
```
并给该测试里每个 `client.post(...)`/`client.get(...)` 增 `headers=h`(create dataset、upload version、list versions 三处)。

- [ ] **Step 5: 运行确认通过**

Run: `cd services/app-server && python -m pytest tests/test_datasets_authz.py tests/test_datasets_api.py -q`
Expected: PASS(both)

- [ ] **Step 6: 提交**
```bash
git add services/app-server/app/api/datasets.py services/app-server/tests/test_datasets_api.py services/app-server/tests/test_datasets_authz.py
git commit -m "feat(app-server): enforce auth and data scope on datasets endpoints"
```

---

### Task 8: training/eval/models/deployments 挂鉴权 + scope(并更新既有测试 + ModelVersion 继承 created_by)

**Files:**
- Modify: `app/api/training.py`、`app/api/eval.py`、`app/api/models.py`、`app/api/deployment.py`
- Modify: `app/services/mlflow_sync.py`(ModelVersion.created_by 继承)
- Modify: `app/services/eval_service.py`、`app/services/deployment_service.py`、`app/services/training_service.py`(set created_by)
- Modify: 既有测试 `tests/test_training_api.py`、`tests/test_eval_api.py`、`tests/test_deployment_api.py`、`tests/test_mlflow_sync.py`
- Test: `tests/test_business_authz.py`

- [ ] **Step 1: 写鉴权测试(新)**
```python
# services/app-server/tests/test_business_authz.py
from fastapi.testclient import TestClient
from tests.conftest import make_user, auth_headers

def _seed_mv(db, owner_id):
    from app.models.dataset import Dataset, DatasetVersion
    from app.models.training import TrainingJob, ModelVersion
    ds = Dataset(name="d", kind="train", task_type="classification", created_by=owner_id)
    db.add(ds); db.commit()
    dv = DatasetVersion(dataset_id=ds.id, version_no=1, storage_uri="s3://x/y",
                        row_count=2, checksum="c", note=""); db.add(dv); db.commit()
    job = TrainingJob(name="j", dataset_version_id=dv.id, base_model="b",
                      task_type="classification", hyperparams={}, created_by=owner_id)
    db.add(job); db.commit()
    mv = ModelVersion(name="m", source_training_job_id=job.id, mlflow_model_name="m",
                      mlflow_version="1", task_type="classification", base_model="b",
                      train_metrics={}, created_by=owner_id); db.add(mv); db.commit()
    return dv.id, mv.id

def test_training_requires_run_and_scope(session_factory):
    S = session_factory; db = S()
    a = make_user(db, codes=("training:read","training:run"), data_scope="own", email="a@x.com")
    b = make_user(db, codes=("training:read",), data_scope="own", email="b@x.com")
    dv_id, _ = _seed_mv(db, a.id)
    aid, bid = a.id, b.id; db.close()
    from app.main import app
    c = TestClient(app)
    # b 无 training:run → 403
    assert c.post("/training-jobs", json={"name":"j2","dataset_version_id":dv_id,
        "base_model":"b","task_type":"classification","hyperparams":{}},
        headers=auth_headers(bid)).status_code == 403
    # a 列表只见自己的;b 列表为空
    assert c.get("/training-jobs", headers=auth_headers(bid)).json() == []

def test_model_versions_scope(session_factory):
    S = session_factory; db = S()
    a = make_user(db, codes=("model:read",), data_scope="own", email="a2@x.com")
    b = make_user(db, codes=("model:read",), data_scope="own", email="b2@x.com")
    _seed_mv(db, a.id)
    aid, bid = a.id, b.id; db.close()
    from app.main import app
    c = TestClient(app)
    assert len(c.get("/model-versions", headers=auth_headers(aid)).json()) == 1
    assert c.get("/model-versions", headers=auth_headers(bid)).json() == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_business_authz.py -q`
Expected: FAIL(当前无鉴权)

- [ ] **Step 3: 改造 training.py**
```python
# services/app-server/app/api/training.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require, apply_scope
from app.auth import require_internal_token
from app.models.user import User
from app.models.training import TrainingJob
from app.schemas.training import TrainingJobCreate, TrainingJobOut
from app.services import training_service
from app.services.mlflow_sync import upsert_model_version_from_result
from pydantic import BaseModel

router = APIRouter(prefix="/training-jobs", tags=["training"])

@router.post("", response_model=TrainingJobOut, status_code=201)
def create(body: TrainingJobCreate, user: User = Depends(require("training:run")),
           db: Session = Depends(get_db)):
    try:
        return training_service.create_and_dispatch(db, body, user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[TrainingJobOut])
def list_jobs(user: User = Depends(require("training:read")), db: Session = Depends(get_db)):
    return db.execute(apply_scope(select(TrainingJob).order_by(TrainingJob.id.desc()),
                                  TrainingJob, user)).scalars().all()

@router.get("/{job_id}", response_model=TrainingJobOut)
def get_job(job_id: int, user: User = Depends(require("training:read")),
            db: Session = Depends(get_db)):
    from app.authz import apply_scope as _scope
    job = db.execute(_scope(select(TrainingJob).where(TrainingJob.id == job_id),
                            TrainingJob, user)).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "not found")
    return job

class TrainResultIn(BaseModel):
    run_id: str
    model_name: str
    version: str
    metrics: dict = {}

@router.post("/internal/{job_id}/result", status_code=201,
             dependencies=[Depends(require_internal_token)])
def report_result(job_id: int, body: TrainResultIn, db: Session = Depends(get_db)):
    mv = upsert_model_version_from_result(db, job_id, body.model_dump())
    return {"model_version_id": mv.id}
```
改 `app/services/training_service.py` 的 `create_and_dispatch` 签名加 `created_by`:
```python
def create_and_dispatch(db, body, created_by=None):
    dv = db.get(DatasetVersion, body.dataset_version_id)
    if not dv:
        raise ValueError("dataset_version not found")
    job = TrainingJob(name=body.name, dataset_version_id=body.dataset_version_id,
                      base_model=body.base_model, task_type=body.task_type.value,
                      hyperparams=body.hyperparams, created_by=created_by)
    db.add(job); db.commit(); db.refresh(job)
    job.celery_task_id = send_train_task(job.id)
    db.commit(); db.refresh(job)
    return job
```

- [ ] **Step 4: 改 mlflow_sync.py 继承 created_by**
在 `upsert_model_version_from_result` 创建 ModelVersion 时加 `created_by=job.created_by`:
```python
    mv = ModelVersion(..., artifact_uri=..., created_by=job.created_by)
```
（`job` 已在函数内取到。）

- [ ] **Step 5: 改造 eval.py / models.py / deployment.py**
`app/api/models.py`:
```python
from app.authz import require, apply_scope
from app.models.user import User
@router.get("", response_model=list[ModelVersionOut])
def list_model_versions(user: User = Depends(require("model:read")), db: Session = Depends(get_db)):
    return db.execute(apply_scope(select(ModelVersion).order_by(ModelVersion.id.desc()),
                                  ModelVersion, user)).scalars().all()
```
`app/api/eval.py`:create 加 `user=Depends(require("eval:run"))` 并把 user.id 传给 service;list/get 加 `require("eval:read")` + `apply_scope`(get 单条非属主 404)。`eval_service.create_and_dispatch(db, body, created_by)` 在 EvalRun 上 set `created_by`。
`app/api/deployment.py`:create 加 `require("deploy:write")`、list 加 `require("deploy:read")`+`apply_scope`、stop 加 `require("deploy:write")`(单条非属主 404)。`deployment_service.create(db, body, created_by)` 在 Deployment set `created_by`。

具体代码(eval.py):
```python
from app.authz import require, apply_scope
from app.auth import get_current_user
from app.models.user import User

@router.post("", response_model=EvalRunOut, status_code=201)
def create(body: EvalRunCreate, user: User = Depends(require("eval:run")),
           db: Session = Depends(get_db)):
    try:
        return eval_service.create_and_dispatch(db, body, user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[EvalRunOut])
def list_runs(dataset_version_id: int | None = None,
              user: User = Depends(require("eval:read")), db: Session = Depends(get_db)):
    q = apply_scope(select(EvalRun).order_by(EvalRun.id.desc()), EvalRun, user)
    if dataset_version_id is not None:
        q = q.where(EvalRun.dataset_version_id == dataset_version_id)
    return db.execute(q).scalars().all()

@router.get("/{run_id}", response_model=EvalRunOut)
def get_run(run_id: int, user: User = Depends(require("eval:read")),
            db: Session = Depends(get_db)):
    run = db.execute(apply_scope(select(EvalRun).where(EvalRun.id == run_id),
                                 EvalRun, user)).scalar_one_or_none()
    if not run:
        raise HTTPException(404, "not found")
    return run
```
`eval_service.create_and_dispatch(db, body, created_by=None)`:`EvalRun(..., created_by=created_by)`。
deployment.py:
```python
from app.authz import require, apply_scope
from app.models.user import User

@router.post("", response_model=DeploymentOut, status_code=201)
def create(body: DeploymentCreate, user: User = Depends(require("deploy:write")),
           db: Session = Depends(get_db)):
    try:
        return deployment_service.create(db, body, user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[DeploymentOut])
def list_deployments(user: User = Depends(require("deploy:read")), db: Session = Depends(get_db)):
    return db.execute(apply_scope(select(Deployment).order_by(Deployment.id.desc()),
                                  Deployment, user)).scalars().all()

@router.post("/{deployment_id}/stop", response_model=DeploymentOut)
def stop(deployment_id: int, user: User = Depends(require("deploy:write")),
         db: Session = Depends(get_db)):
    from app.authz import apply_scope as _s
    dep = db.execute(_s(select(Deployment).where(Deployment.id == deployment_id),
                        Deployment, user)).scalar_one_or_none()
    if not dep:
        raise HTTPException(404, "deployment not found")
    try:
        return deployment_service.stop(db, deployment_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
```
`deployment_service.create(db, body, created_by=None)`:`Deployment(..., created_by=created_by)`。

- [ ] **Step 6: 更新既有测试带 token + 新签名**
- `test_training_api.py`:用 `make_user(codes=("*",))` + `auth_headers` 给 `/training-jobs` POST 带 header;`create_and_dispatch` 现多一个参数,API 测试走 HTTP 不受影响。
- `test_eval_api.py`、`test_deployment_api.py`:同理给请求带全权用户 header。
- `test_mlflow_sync.py`:`upsert_model_version_from_result` 仍按原签名;但 ModelVersion 现需 `created_by`(nullable,job.created_by 可为 None)——测试里 job 无 created_by 时 mv.created_by=None,断言不变即可。

为每个受影响测试在建 client 后加:
```python
    from tests.conftest import make_user, auth_headers
    _d = dbmod.SessionLocal(); _root = make_user(_d, codes=("*",), data_scope="all", email="root2@x.com")
    H = auth_headers(_root.id); _d.close()
```
并给对应业务请求加 `headers=H`。

- [ ] **Step 7: 运行确认通过**

Run: `cd services/app-server && python -m pytest -q`
Expected: 全套 PASS

- [ ] **Step 8: 提交**
```bash
git add services/app-server/app/api services/app-server/app/services services/app-server/tests
git commit -m "feat(app-server): enforce auth/scope on training, eval, models, deployments"
```

---

### Task 9: 内部 token 护栏 worker 接线

**Files:**
- Modify: `services/train-worker/worker/config.py`(加 internal_token)
- Modify: `services/train-worker/worker/tasks.py`(report_result 带 header)
- Test: `services/app-server/tests/test_internal_token.py`

- [ ] **Step 1: 写失败测试**
```python
# services/app-server/tests/test_internal_token.py
from fastapi.testclient import TestClient
from tests.conftest import make_user

def test_internal_callback_requires_token(session_factory):
    S = session_factory; db = S()
    from app.models.dataset import Dataset, DatasetVersion
    from app.models.training import TrainingJob
    owner = make_user(db, codes=("*",), email="o@x.com")
    job = TrainingJob(name="j", dataset_version_id=1, base_model="b",
                      task_type="classification", hyperparams={}, created_by=owner.id)
    db.add(job); db.commit(); jid = job.id; db.close()
    from app.main import app
    c = TestClient(app)
    payload = {"run_id":"r","model_name":"m","version":"1","metrics":{}}
    assert c.post(f"/training-jobs/internal/{jid}/result", json=payload).status_code == 401
    ok = c.post(f"/training-jobs/internal/{jid}/result", json=payload,
                headers={"X-Internal-Token": "modelforge-internal"})
    assert ok.status_code == 201
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_internal_token.py -q`
Expected: FAIL — 当前内部端点无 token 校验(返回 201 而非 401)
（注:Task 8 已给内部端点加 `dependencies=[Depends(require_internal_token)]`;若 Task 8 已合入,则此测试的 401 分支应已通过——本任务负责 worker 侧接线与该测试。若 Task 8 尚未加,请确保内部端点已挂 `require_internal_token`。)

- [ ] **Step 3: worker 接线**
`worker/config.py` Settings 增:`internal_token: str = "modelforge-internal"`。
`worker/tasks.py` 的 `report_result` 增 header:
```python
def report_result(training_job_id, run_id, model_name, version, metrics):
    requests.post(
        f"{settings.app_server_url}/training-jobs/internal/{training_job_id}/result",
        json={"run_id": run_id, "model_name": model_name, "version": version,
              "metrics": {k: float(v) for k, v in metrics.items()
                          if isinstance(v, (int, float))}},
        headers={"X-Internal-Token": settings.internal_token}, timeout=10)
```

- [ ] **Step 4: 运行确认通过**

Run:
```bash
cd services/app-server && python -m pytest tests/test_internal_token.py -q   # PASS
cd ../train-worker && python -m pytest -q -m "not slow"                       # 仍绿(report_result 被 stub)
```

- [ ] **Step 5: 提交**
```bash
git add services/train-worker/worker/config.py services/train-worker/worker/tasks.py services/app-server/tests/test_internal_token.py
git commit -m "feat: protect internal training callback with X-Internal-Token"
```

---

# 阶段 3:超管管理 API

### Task 10: 用户管理 API + 最后超管护栏

**Files:**
- Create: `services/app-server/app/schemas/rbac.py`
- Create: `services/app-server/app/services/user_service.py`
- Create: `services/app-server/app/api/users.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_users_api.py`

- [ ] **Step 1: 写失败测试**
```python
# services/app-server/tests/test_users_api.py
from fastapi.testclient import TestClient
from tests.conftest import auth_headers

def _seed(db):
    from app.bootstrap import seed
    from sqlalchemy import select
    from app.models.user import User
    from app.models.rbac import Role
    seed(db)
    superadmin = db.execute(select(Role).where(Role.name=="superadmin")).scalar_one()
    admin = db.execute(select(User).where(User.role_id==superadmin.id)).scalar_one()
    member_role = db.execute(select(Role).where(Role.name=="member")).scalar_one()
    return admin.id, member_role.id, superadmin.id

def test_user_management_flow(session_factory):
    S = session_factory; db = S()
    admin_id, member_role_id, superadmin_role_id = _seed(db); db.close()
    from app.main import app
    c = TestClient(app)
    H = auth_headers(admin_id)
    # 建用户
    r = c.post("/users", json={"name":"u1","email":"u1@x.com","password":"pw",
                               "role_id": member_role_id}, headers=H)
    assert r.status_code == 201
    uid = r.json()["id"]
    # 列表含两人
    assert len(c.get("/users", headers=H).json()) == 2
    # 改角色/启停
    assert c.patch(f"/users/{uid}", json={"is_active": False}, headers=H).status_code == 200
    # 无 user:manage 的人 403
    login = c.post("/auth/login", json={"email":"u1@x.com","password":"pw"})
    # u1 被停用,登录应 401
    assert login.status_code == 401
    # 最后一个 superadmin 不可停用
    r = c.patch(f"/users/{admin_id}", json={"is_active": False}, headers=H)
    assert r.status_code == 422

def test_requires_user_manage(session_factory):
    from tests.conftest import make_user
    S = session_factory; db = S()
    plain = make_user(db, codes=("dataset:read",), email="p@x.com")
    pid = plain.id; db.close()
    from app.main import app
    c = TestClient(app)
    assert c.get("/users", headers=auth_headers(pid)).status_code == 403
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_users_api.py -q`
Expected: FAIL — 404/ModuleNotFound

- [ ] **Step 3: 实现 schema**
```python
# services/app-server/app/schemas/rbac.py
from pydantic import BaseModel

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role_id: int | None = None

class UserUpdate(BaseModel):
    role_id: int | None = None
    is_active: bool | None = None

class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role_id: int | None
    is_active: bool
    class Config: from_attributes = True

class PasswordReset(BaseModel):
    password: str

class RoleCreate(BaseModel):
    name: str
    description: str = ""
    data_scope: str = "own"
    permission_codes: list[str] = []

class RoleUpdate(BaseModel):
    description: str | None = None
    data_scope: str | None = None
    permission_codes: list[str] | None = None

class RoleOut(BaseModel):
    id: int
    name: str
    description: str
    data_scope: str
    is_system: bool
    permissions: list[str]

class PermissionOut(BaseModel):
    code: str
    description: str
```

- [ ] **Step 4: 实现 user_service(含最后超管护栏)**
```python
# services/app-server/app/services/user_service.py
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.rbac import Role
from app.auth import hash_password

SUPERADMIN = "superadmin"

def _superadmin_role_id(db: Session):
    r = db.execute(select(Role).where(Role.name == SUPERADMIN)).scalar_one_or_none()
    return r.id if r else None

def _active_superadmin_count(db: Session) -> int:
    sid = _superadmin_role_id(db)
    if sid is None:
        return 0
    return db.execute(select(func.count()).select_from(User)
                      .where(User.role_id == sid, User.is_active.is_(True))).scalar()

def create_user(db: Session, body) -> User:
    if db.execute(select(User).where(User.email == body.email)).scalar_one_or_none():
        raise ValueError("email already exists")
    u = User(name=body.name, email=body.email,
             password_hash=hash_password(body.password), role_id=body.role_id, is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u

def update_user(db: Session, user_id: int, body) -> User:
    u = db.get(User, user_id)
    if not u:
        raise ValueError("user not found")
    sid = _superadmin_role_id(db)
    last_admin = (u.role_id == sid and u.is_active and _active_superadmin_count(db) == 1)
    if last_admin and (body.is_active is False or
                       (body.role_id is not None and body.role_id != sid)):
        raise PermissionError("cannot demote or deactivate the last superadmin")
    if body.role_id is not None:
        u.role_id = body.role_id
    if body.is_active is not None:
        u.is_active = body.is_active
    db.commit(); db.refresh(u)
    return u

def reset_password(db: Session, user_id: int, password: str) -> User:
    u = db.get(User, user_id)
    if not u:
        raise ValueError("user not found")
    u.password_hash = hash_password(password); db.commit(); db.refresh(u)
    return u
```

- [ ] **Step 5: 实现 users 路由**
```python
# services/app-server/app/api/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.schemas.rbac import UserCreate, UserUpdate, UserOut, PasswordReset
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])

@router.post("", response_model=UserOut, status_code=201)
def create(body: UserCreate, _: User = Depends(require("user:manage")),
           db: Session = Depends(get_db)):
    try:
        return user_service.create_user(db, body)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[UserOut])
def list_users(_: User = Depends(require("user:manage")), db: Session = Depends(get_db)):
    return db.execute(select(User).order_by(User.id)).scalars().all()

@router.patch("/{user_id}", response_model=UserOut)
def update(user_id: int, body: UserUpdate, _: User = Depends(require("user:manage")),
           db: Session = Depends(get_db)):
    try:
        return user_service.update_user(db, user_id, body)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except PermissionError as e:
        raise HTTPException(422, str(e))

@router.post("/{user_id}/reset-password", response_model=UserOut)
def reset_pw(user_id: int, body: PasswordReset, _: User = Depends(require("user:manage")),
             db: Session = Depends(get_db)):
    try:
        return user_service.reset_password(db, user_id, body.password)
    except ValueError as e:
        raise HTTPException(404, str(e))
```
`app/main.py` 追加 `from app.api import users` + `app.include_router(users.router)`。

- [ ] **Step 6: 运行确认通过** `python -m pytest tests/test_users_api.py -q` → PASS;全套 `python -m pytest -q` 绿。

- [ ] **Step 7: 提交**
```bash
git add services/app-server/app/schemas/rbac.py services/app-server/app/services/user_service.py services/app-server/app/api/users.py services/app-server/app/main.py services/app-server/tests/test_users_api.py
git commit -m "feat(app-server): user management API with last-superadmin guard"
```

---

### Task 11: 角色管理 API + 权限目录

**Files:**
- Create: `services/app-server/app/services/role_service.py`
- Create: `services/app-server/app/api/roles.py`
- Modify: `services/app-server/app/main.py`
- Test: `services/app-server/tests/test_roles_api.py`

- [ ] **Step 1: 写失败测试**
```python
# services/app-server/tests/test_roles_api.py
from fastapi.testclient import TestClient
from tests.conftest import auth_headers

def _admin(db):
    from app.bootstrap import seed
    from sqlalchemy import select
    from app.models.user import User
    from app.models.rbac import Role
    seed(db)
    sa = db.execute(select(Role).where(Role.name=="superadmin")).scalar_one()
    return db.execute(select(User).where(User.role_id==sa.id)).scalar_one().id, sa.id

def test_role_crud(session_factory):
    S = session_factory; db = S()
    admin_id, sa_id = _admin(db); db.close()
    from app.main import app
    c = TestClient(app)
    H = auth_headers(admin_id)
    assert {p["code"] for p in c.get("/permissions", headers=H).json()} >= {"dataset:read","*"}
    # 建自定义角色
    r = c.post("/roles", json={"name":"labeler","data_scope":"own",
        "permission_codes":["dataset:read","dataset:write"]}, headers=H)
    assert r.status_code == 201 and set(r.json()["permissions"]) == {"dataset:read","dataset:write"}
    rid = r.json()["id"]
    # 改权限集
    r = c.patch(f"/roles/{rid}", json={"permission_codes":["dataset:read"]}, headers=H)
    assert set(r.json()["permissions"]) == {"dataset:read"}
    # 系统角色拒改/删
    assert c.patch(f"/roles/{sa_id}", json={"description":"x"}, headers=H).status_code == 400
    assert c.delete(f"/roles/{sa_id}", headers=H).status_code == 400
    # 删自定义角色
    assert c.delete(f"/roles/{rid}", headers=H).status_code == 200

def test_roles_requires_role_manage(session_factory):
    from tests.conftest import make_user
    S = session_factory; db = S()
    plain = make_user(db, codes=("dataset:read",), email="pp@x.com")
    pid = plain.id; db.close()
    from app.main import app
    c = TestClient(app)
    assert c.get("/roles", headers=auth_headers(pid)).status_code == 403
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_roles_api.py -q`
Expected: FAIL — 404/ModuleNotFound

- [ ] **Step 3: 实现 role_service**
```python
# services/app-server/app/services/role_service.py
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.rbac import Role, Permission
from app.models.user import User

def _perms(db: Session, codes):
    found = db.execute(select(Permission).where(Permission.code.in_(codes))).scalars().all()
    known = {p.code for p in found}
    missing = set(codes) - known
    if missing:
        raise ValueError(f"unknown permission codes: {sorted(missing)}")
    return found

def create_role(db: Session, body) -> Role:
    if db.execute(select(Role).where(Role.name == body.name)).scalar_one_or_none():
        raise ValueError("role name exists")
    r = Role(name=body.name, description=body.description, data_scope=body.data_scope,
             is_system=False, permissions=_perms(db, body.permission_codes))
    db.add(r); db.commit(); db.refresh(r)
    return r

def update_role(db: Session, role_id: int, body) -> Role:
    r = db.get(Role, role_id)
    if not r:
        raise ValueError("role not found")
    if r.is_system:
        raise PermissionError("system role is immutable")
    if body.description is not None:
        r.description = body.description
    if body.data_scope is not None:
        r.data_scope = body.data_scope
    if body.permission_codes is not None:
        r.permissions = _perms(db, body.permission_codes)
    db.commit(); db.refresh(r)
    return r

def delete_role(db: Session, role_id: int) -> None:
    r = db.get(Role, role_id)
    if not r:
        raise ValueError("role not found")
    if r.is_system:
        raise PermissionError("system role cannot be deleted")
    in_use = db.execute(select(User).where(User.role_id == role_id)).first()
    if in_use:
        raise ValueError("role is assigned to users")  # 409 by caller
    db.delete(r); db.commit()
```

- [ ] **Step 4: 实现 roles 路由 + 权限目录**
```python
# services/app-server/app/api/roles.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.models.rbac import Role, Permission
from app.schemas.rbac import RoleCreate, RoleUpdate, RoleOut, PermissionOut
from app.services import role_service

router = APIRouter(tags=["roles"])

def _role_out(r: Role) -> RoleOut:
    return RoleOut(id=r.id, name=r.name, description=r.description,
                   data_scope=r.data_scope, is_system=r.is_system,
                   permissions=sorted(p.code for p in r.permissions))

@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(_: User = Depends(require("role:manage")), db: Session = Depends(get_db)):
    return db.execute(select(Permission).order_by(Permission.code)).scalars().all()

@router.get("/roles", response_model=list[RoleOut])
def list_roles(_: User = Depends(require("role:manage")), db: Session = Depends(get_db)):
    return [_role_out(r) for r in db.execute(select(Role).order_by(Role.id)).scalars()]

@router.post("/roles", response_model=RoleOut, status_code=201)
def create(body: RoleCreate, _: User = Depends(require("role:manage")),
           db: Session = Depends(get_db)):
    try:
        return _role_out(role_service.create_role(db, body))
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.patch("/roles/{role_id}", response_model=RoleOut)
def update(role_id: int, body: RoleUpdate, _: User = Depends(require("role:manage")),
           db: Session = Depends(get_db)):
    try:
        return _role_out(role_service.update_role(db, role_id, body))
    except ValueError as e:
        raise HTTPException(404, str(e))
    except PermissionError as e:
        raise HTTPException(400, str(e))

@router.delete("/roles/{role_id}")
def delete(role_id: int, _: User = Depends(require("role:manage")),
           db: Session = Depends(get_db)):
    try:
        role_service.delete_role(db, role_id); return {"deleted": True}
    except PermissionError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        msg = str(e)
        raise HTTPException(409 if "assigned" in msg else 404, msg)
```
`app/main.py` 追加 `from app.api import roles` + `app.include_router(roles.router)`。

- [ ] **Step 5: 运行确认通过** `python -m pytest tests/test_roles_api.py -q` → PASS;全套 `python -m pytest -q` 绿。

- [ ] **Step 6: 提交**
```bash
git add services/app-server/app/services/role_service.py services/app-server/app/api/roles.py services/app-server/app/main.py services/app-server/tests/test_roles_api.py
git commit -m "feat(app-server): role management API and permission catalog"
```

---

# 阶段 4:前端

### Task 12: 前端认证(登录 + 守卫 + 拦截器)

**Files:**
- Create: `frontend/src/auth.ts`
- Create: `frontend/src/context/AuthContext.tsx`
- Create: `frontend/src/pages/LoginPage.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`、`frontend/src/main.tsx`

- [ ] **Step 1: auth.ts + 拦截器**
```ts
// frontend/src/auth.ts
import { api } from "./api/client";

export type Me = { id: number; name: string; email: string; role: string | null; data_scope: string; permissions: string[] };
const TOKEN_KEY = "mf_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export async function login(email: string, password: string): Promise<Me> {
  const r = await api.post("/auth/login", { email, password });
  setToken(r.data.access_token);
  return r.data.user as Me;
}
export const fetchMe = () => api.get<Me>("/auth/me").then(r => r.data);
```
在 `frontend/src/api/client.ts` 顶部 axios 实例后加拦截器:
```ts
api.interceptors.request.use(cfg => {
  const t = localStorage.getItem("mf_token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});
api.interceptors.response.use(r => r, err => {
  if (err.response?.status === 401) {
    localStorage.removeItem("mf_token");
    if (location.pathname !== "/login") location.href = "/login";
  }
  return Promise.reject(err);
});
```

- [ ] **Step 2: AuthContext**
```tsx
// frontend/src/context/AuthContext.tsx
import { createContext, useContext, useEffect, useState } from "react";
import { fetchMe, getToken, clearToken, type Me } from "../auth";

type Ctx = { me: Me | null; loading: boolean; can: (c: string) => boolean; logout: () => void; setMe: (m: Me | null) => void };
const AuthCtx = createContext<Ctx>(null as unknown as Ctx);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!getToken()) { setLoading(false); return; }
    fetchMe().then(setMe).catch(() => clearToken()).finally(() => setLoading(false));
  }, []);
  const can = (c: string) => !!me && (me.permissions.includes("*") || me.permissions.includes(c));
  const logout = () => { clearToken(); setMe(null); location.href = "/login"; };
  return <AuthCtx.Provider value={{ me, loading, can, logout, setMe }}>{children}</AuthCtx.Provider>;
}
```

- [ ] **Step 3: LoginPage**
```tsx
// frontend/src/pages/LoginPage.tsx
import { useState } from "react";
import { login } from "../auth";
import { useAuth } from "../context/AuthContext";

export function LoginPage() {
  const { setMe } = useAuth();
  const [email, setEmail] = useState(""); const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const submit = async () => {
    try { const me = await login(email, pw); setMe(me); location.href = "/"; }
    catch { setErr("登录失败"); }
  };
  return (
    <div style={{ maxWidth: 320, margin: "80px auto" }}>
      <h2>登录 ModelForge</h2>
      <input placeholder="email" value={email} onChange={e => setEmail(e.target.value)} style={{ display: "block", width: "100%", marginBottom: 8 }} />
      <input placeholder="password" type="password" value={pw} onChange={e => setPw(e.target.value)} style={{ display: "block", width: "100%", marginBottom: 8 }} />
      <button onClick={submit}>登录</button>
      {err && <p style={{ color: "red" }}>{err}</p>}
    </div>
  );
}
```

- [ ] **Step 4: main.tsx 包 AuthProvider + App 守卫**
`frontend/src/main.tsx`:用 `<AuthProvider>` 包住 `<App/>`(保留既有渲染)。
`frontend/src/App.tsx`:加登录守卫与登出/导航(整体替换):
```tsx
import { DatasetsPage } from "./pages/DatasetsPage";
import { DatasetDetailPage } from "./pages/DatasetDetailPage";
import { TrainingPage } from "./pages/TrainingPage";
import { ModelsPage } from "./pages/ModelsPage";
import { EvalPage } from "./pages/EvalPage";
import { DeployPage } from "./pages/DeployPage";
import { LoginPage } from "./pages/LoginPage";
import { UsersPage } from "./pages/UsersPage";
import { RolesPage } from "./pages/RolesPage";
import { useAuth } from "./context/AuthContext";

export default function App() {
  const { me, loading, can, logout } = useAuth();
  const path = window.location.pathname;
  if (path === "/login") return <LoginPage />;
  if (loading) return <div>加载中…</div>;
  if (!me) { location.href = "/login"; return null; }

  const m = path.match(/^\/datasets\/(\d+)$/);
  let page = <DatasetsPage />;
  if (m) page = <DatasetDetailPage id={Number(m[1])} />;
  else if (path === "/training") page = <TrainingPage />;
  else if (path === "/models") page = <ModelsPage />;
  else if (path === "/eval") page = <EvalPage />;
  else if (path === "/deploy") page = <DeployPage />;
  else if (path === "/users") page = <UsersPage />;
  else if (path === "/roles") page = <RolesPage />;
  return (
    <div>
      <nav style={{ display: "flex", gap: 12, marginBottom: 16, alignItems: "center" }}>
        <a href="/">数据集</a><a href="/training">训练</a><a href="/models">模型</a>
        <a href="/eval">评估</a><a href="/deploy">部署</a>
        {can("user:manage") && <a href="/users">用户</a>}
        {can("role:manage") && <a href="/roles">角色</a>}
        <span style={{ marginLeft: "auto" }}>{me.name} ({me.role}) <button onClick={logout}>登出</button></span>
      </nav>
      {page}
    </div>
  );
}
```

- [ ] **Step 5: 构建** `cd frontend && npm run build` → exit 0(此时 UsersPage/RolesPage 还不存在 → 先建空占位以通过编译,或本任务连同 Task 13 一起建。为不阻塞构建,本任务先创建最小占位):
建 `frontend/src/pages/UsersPage.tsx`、`RolesPage.tsx` 占位:
```tsx
export function UsersPage() { return <div><h2>用户</h2></div>; }
```
```tsx
export function RolesPage() { return <div><h2>角色</h2></div>; }
```
`npm run build` 必须 exit 0。

- [ ] **Step 6: 提交**
```bash
git add frontend/src
git commit -m "feat(frontend): auth context, login page and route guard"
```

---

### Task 13: 前端用户/角色管理页

**Files:**
- Modify: `frontend/src/api/client.ts`(增 rbac API)
- Modify: `frontend/src/pages/UsersPage.tsx`、`frontend/src/pages/RolesPage.tsx`

- [ ] **Step 1: client.ts 增 rbac API**
```ts
// frontend/src/api/client.ts  (追加)
export type AdminUser = { id: number; name: string; email: string; role_id: number | null; is_active: boolean };
export type Role = { id: number; name: string; description: string; data_scope: string; is_system: boolean; permissions: string[] };
export type Permission = { code: string; description: string };
export const listUsers = () => api.get<AdminUser[]>("/users").then(r => r.data);
export const createUser = (b: { name: string; email: string; password: string; role_id: number | null }) => api.post<AdminUser>("/users", b).then(r => r.data);
export const updateUser = (id: number, b: { role_id?: number | null; is_active?: boolean }) => api.patch<AdminUser>(`/users/${id}`, b).then(r => r.data);
export const resetPassword = (id: number, password: string) => api.post(`/users/${id}/reset-password`, { password }).then(r => r.data);
export const listRoles = () => api.get<Role[]>("/roles").then(r => r.data);
export const createRole = (b: { name: string; description: string; data_scope: string; permission_codes: string[] }) => api.post<Role>("/roles", b).then(r => r.data);
export const updateRole = (id: number, b: { permission_codes?: string[]; data_scope?: string; description?: string }) => api.patch<Role>(`/roles/${id}`, b).then(r => r.data);
export const deleteRole = (id: number) => api.delete(`/roles/${id}`).then(r => r.data);
export const listPermissions = () => api.get<Permission[]>("/permissions").then(r => r.data);
```

- [ ] **Step 2: UsersPage(整体替换占位)**
```tsx
// frontend/src/pages/UsersPage.tsx
import { useEffect, useState } from "react";
import { listUsers, createUser, updateUser, resetPassword, listRoles,
         type AdminUser, type Role } from "../api/client";

export function UsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [f, setF] = useState({ name: "", email: "", password: "", role_id: "" });
  const reload = () => { listUsers().then(setUsers); listRoles().then(setRoles); };
  useEffect(() => { reload(); }, []);
  return (
    <div>
      <h2>用户管理</h2>
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        <input placeholder="name" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} />
        <input placeholder="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} />
        <input placeholder="password" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} />
        <select value={f.role_id} onChange={e => setF({ ...f, role_id: e.target.value })}>
          <option value="">(角色)</option>
          {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        <button disabled={!f.name || !f.email || !f.password} onClick={() =>
          createUser({ name: f.name, email: f.email, password: f.password,
                       role_id: f.role_id ? Number(f.role_id) : null })
            .then(() => { setF({ name: "", email: "", password: "", role_id: "" }); reload(); })}>新建用户</button>
      </div>
      <table><thead><tr><th>#</th><th>名称</th><th>email</th><th>角色</th><th>状态</th><th></th></tr></thead>
        <tbody>{users.map(u => <tr key={u.id}>
          <td>{u.id}</td><td>{u.name}</td><td>{u.email}</td>
          <td><select value={u.role_id ?? ""} onChange={e =>
            updateUser(u.id, { role_id: e.target.value ? Number(e.target.value) : null }).then(reload)}>
            <option value="">(无)</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select></td>
          <td>{u.is_active ? "在职" : "停用"}</td>
          <td>
            <button onClick={() => updateUser(u.id, { is_active: !u.is_active }).then(reload)}>{u.is_active ? "停用" : "启用"}</button>
            <button onClick={() => { const p = prompt("新密码"); if (p) resetPassword(u.id, p); }}>改密</button>
          </td></tr>)}</tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: RolesPage(整体替换占位)**
```tsx
// frontend/src/pages/RolesPage.tsx
import { useEffect, useState } from "react";
import { listRoles, createRole, updateRole, deleteRole, listPermissions,
         type Role, type Permission } from "../api/client";

export function RolesPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [perms, setPerms] = useState<Permission[]>([]);
  const [name, setName] = useState(""); const [scope, setScope] = useState("own");
  const [sel, setSel] = useState<string[]>([]);
  const reload = () => { listRoles().then(setRoles); listPermissions().then(setPerms); };
  useEffect(() => { reload(); }, []);
  const toggle = (c: string) => setSel(s => s.includes(c) ? s.filter(x => x !== c) : [...s, c]);
  return (
    <div>
      <h2>角色管理</h2>
      <div style={{ marginBottom: 12 }}>
        <input placeholder="角色名" value={name} onChange={e => setName(e.target.value)} />
        <select value={scope} onChange={e => setScope(e.target.value)}>
          <option value="own">own</option><option value="all">all</option>
        </select>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "8px 0" }}>
          {perms.filter(p => p.code !== "*").map(p =>
            <label key={p.code}><input type="checkbox" checked={sel.includes(p.code)} onChange={() => toggle(p.code)} />{p.code}</label>)}
        </div>
        <button disabled={!name} onClick={() =>
          createRole({ name, description: "", data_scope: scope, permission_codes: sel })
            .then(() => { setName(""); setSel([]); reload(); })}>新建角色</button>
      </div>
      <table><thead><tr><th>角色</th><th>scope</th><th>权限</th><th></th></tr></thead>
        <tbody>{roles.map(r => <tr key={r.id}>
          <td>{r.name}{r.is_system ? " (系统)" : ""}</td><td>{r.data_scope}</td>
          <td style={{ maxWidth: 360 }}>{r.permissions.join(", ")}</td>
          <td>{!r.is_system && <button onClick={() => deleteRole(r.id).then(reload).catch(() => alert("删除失败(可能被用户引用)"))}>删除</button>}</td>
        </tr>)}</tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: 构建** `cd frontend && npm run build` → exit 0,dist/ 产出。修 TS 报错(type-only import)不改行为。

- [ ] **Step 5: 提交**
```bash
git add frontend/src
git commit -m "feat(frontend): user and role management pages"
```

---

## 自查(Self-Review)

**Spec 覆盖:**
- §2 权限目录 → Task 3 PERMISSION_CATALOG ✅
- §3 数据模型(roles/permissions/role_permissions + users 改造 + created_by)→ Task 1/6 ✅
- §4 JWT 认证(login/me/get_current_user)→ Task 2/4 ✅
- §5 鉴权 + 数据范围(require/apply_scope + 端点接入)→ Task 5/7/8 ✅
- §6 超管管理 API(users/roles/permissions + 护栏)→ Task 10/11 ✅
- §7 引导 seed + 最后超管护栏 → Task 3/10 ✅
- §8 内部 token → Task 8(端点)/Task 9(worker)✅
- §9 前端(登录/守卫/管理页/显隐)→ Task 12/13 ✅
- §10 测试 → 各任务内置 ✅

**占位符扫描:** 无 TBD;每步含完整代码。

**类型一致性:** `require(code)`/`apply_scope(stmt,model,user)`/`permission_codes(user)`/`effective_scope` 跨 Task 5/7/8 一致;`create_and_dispatch(db,body,created_by)`(training/eval)与 `deployment_service.create(db,body,created_by)` 新签名在 Task 8 改动并同步更新调用方与既有测试;`make_user`/`auth_headers`/`session_factory` 在 Task 2 conftest 定义,后续任务统一引用;`ModelVersion.created_by` 在 Task 6 加列、Task 8 由 mlflow_sync 继承;前端 `useAuth().can(code)` 与 `/auth/me` 的 permissions 一致。

**关键风险/前置:**
- Task 1 删除 users.role 列是破坏式;现无真实用户,迁移即可。
- Task 7/8 给端点加鉴权后,**所有既有端点测试必须在同任务内更新带 token**,否则全红;已在对应步骤明确。
- bcrypt 直接用(非 passlib),避开 passlib+bcrypt 版本探测坑。
- seed 需在迁移后跑(`python -m app.bootstrap`)才能登录;e2e/部署文档应加这一步。
