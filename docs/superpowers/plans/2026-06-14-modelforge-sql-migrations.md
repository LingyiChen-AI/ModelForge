# ModelForge SQL Migrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用「编号 SQL 迁移文件 + 自建 runner + 启动自动应用」替换 Alembic。

**Architecture:** `db/migrations/NNN_*.sql` 按编号执行;`app/migrate.py` runner 用 `schema_migrations` 表跟踪、只跑没跑过的;app 启动(仅 PostgreSQL + 开关)自动应用。SQL 用幂等 DDL/DML(`IF NOT EXISTS` / `ON CONFLICT`),对现有库重跑无害。SQLAlchemy 模型仍是查询层;测试用 SQLite + ORM,不受影响。

**Tech Stack:** FastAPI(lifespan)、SQLAlchemy + psycopg、bcrypt、pytest、PostgreSQL。

参考 spec:`docs/superpowers/specs/2026-06-14-modelforge-sql-migrations-design.md`。前置:dev 环境有运行中的 PostgreSQL(`postgresql://modelforge:modelforge@localhost:5432/modelforge`,可建/删数据库)。

---

## 文件结构

```
services/app-server/
  app/migrate.py              # 新:runner(run_migrations / run / __main__)
  app/config.py               # 改:增 run_migrations_on_startup
  app/main.py                 # 改:lifespan 启动自动迁移
  db/migrations/
    001_init_schema.sql       # 新:全量建表(IF NOT EXISTS),从模型导出
    002_seed_rbac.sql         # 新:幂等种子(权限/角色/关联/初始超管)
  tests/conftest.py           # 改:关 run_migrations_on_startup
  tests/test_migrate.py       # 新:runner 幂等性(临时 PG 库)
  tests/test_startup_migrate.py # 新:启动开关守卫
删除:alembic/、alembic.ini、scripts/dump_schema.py、db/init.sql;pyproject 去掉 alembic
```

---

### Task 1: 迁移 runner + config 开关

**Files:**
- Modify: `services/app-server/app/config.py`
- Create: `services/app-server/app/migrate.py`
- Test: `services/app-server/tests/test_migrate.py`

- [ ] **Step 1: config 增开关**
在 `app/config.py` 的 `Settings` 增一行:
```python
    run_migrations_on_startup: bool = True
```

- [ ] **Step 2: 写失败测试**(临时 PG 库 + 临时迁移目录,验证按序应用、幂等、多语句文件)
```python
# services/app-server/tests/test_migrate.py
import psycopg, pytest
from sqlalchemy import create_engine, text

PG_ADMIN = "postgresql://modelforge:modelforge@localhost:5432/modelforge"
PG_TEST = "postgresql+psycopg://modelforge:modelforge@localhost:5432/mf_migtest"

@pytest.fixture
def pg_engine():
    admin = psycopg.connect(PG_ADMIN, autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS mf_migtest")
    admin.execute("CREATE DATABASE mf_migtest")
    eng = create_engine(PG_TEST)
    try:
        yield eng
    finally:
        eng.dispose()
        admin.execute("DROP DATABASE IF EXISTS mf_migtest")
        admin.close()

def test_runner_applies_in_order_idempotent(pg_engine, tmp_path):
    # 001 是多语句文件(验证 runner 支持一次执行多条)
    (tmp_path / "001_a.sql").write_text(
        "CREATE TABLE IF NOT EXISTS t_a (id INT PRIMARY KEY);\n"
        "CREATE TABLE IF NOT EXISTS t_a2 (id INT PRIMARY KEY);")
    (tmp_path / "002_b.sql").write_text(
        "CREATE TABLE IF NOT EXISTS t_b (id INT PRIMARY KEY);")
    from app.migrate import run_migrations
    assert run_migrations(pg_engine, tmp_path) == ["001_a.sql", "002_b.sql"]
    assert run_migrations(pg_engine, tmp_path) == []   # 重跑 0 个
    with pg_engine.connect() as c:
        versions = {r[0] for r in c.execute(text("SELECT version FROM schema_migrations"))}
        ntables = c.execute(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name IN ('t_a','t_a2','t_b')")).scalar()
    assert versions == {"001_a.sql", "002_b.sql"}
    assert ntables == 3
```

- [ ] **Step 3: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_migrate.py -q`
Expected: FAIL — ModuleNotFoundError: app.migrate

- [ ] **Step 4: 实现 runner**
```python
# services/app-server/app/migrate.py
from pathlib import Path

from app.db import engine

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


def run_migrations(eng=engine, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply not-yet-applied *.sql files in filename order. Idempotent."""
    with eng.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT now())")
        done = {row[0] for row in conn.exec_driver_sql(
            "SELECT version FROM schema_migrations")}
    applied: list[str] = []
    for path in sorted(Path(migrations_dir).glob("*.sql")):
        if path.name in done:
            continue
        sql = path.read_text()
        with eng.begin() as conn:
            conn.exec_driver_sql(sql)
            conn.exec_driver_sql(
                "INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
        applied.append(path.name)
    return applied


def run() -> None:
    applied = run_migrations()
    print(f"applied: {applied or '(none)'}")


if __name__ == "__main__":
    run()
```

- [ ] **Step 5: 运行确认通过**

Run: `cd services/app-server && python -m pytest tests/test_migrate.py -q`
Expected: PASS (needs the running dev PostgreSQL; the fixture creates/drops `mf_migtest`).

- [ ] **Step 6: 提交**
```bash
git add services/app-server/app/config.py services/app-server/app/migrate.py services/app-server/tests/test_migrate.py
git commit -m "feat(app-server): SQL migration runner with schema_migrations tracking"
```

---

### Task 2: 生成 001_init_schema.sql + 写 002_seed_rbac.sql

**Files:**
- Create: `services/app-server/db/migrations/001_init_schema.sql`
- Create: `services/app-server/db/migrations/002_seed_rbac.sql`
- Test: `services/app-server/tests/test_migrations_apply.py`

- [ ] **Step 1: 生成 001_init_schema.sql(从当前模型导出,IF NOT EXISTS)**
Run(from `services/app-server`):
```bash
python - <<'PY'
from pathlib import Path
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from app.models import Base
import app.models  # noqa: F401

out = ["-- 001 init schema (auto-generated baseline from SQLAlchemy models, idempotent)"]
d = postgresql.dialect()
for t in Base.metadata.sorted_tables:
    out.append(str(CreateTable(t, if_not_exists=True).compile(dialect=d)).strip() + ";")
p = Path("db/migrations/001_init_schema.sql")
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text("\n\n".join(out) + "\n")
print("wrote", p, "with", len(Base.metadata.sorted_tables), "tables")
PY
```
Confirm the file contains `CREATE TABLE IF NOT EXISTS permissions (...)` … through all 10 tables (permissions, roles, role_permissions, users, datasets, dataset_versions, training_jobs, model_versions, deployments, eval_runs), in that FK-dependency order.

- [ ] **Step 2: 生成 admin 密码哈希**
Run: `python -c "import bcrypt; print(bcrypt.hashpw(b'admin12345', bcrypt.gensalt()).decode())"`
Copy the printed hash (starts with `$2b$`). Use it as `<HASH>` in the next step.

- [ ] **Step 3: 写 002_seed_rbac.sql**(把 `<HASH>` 替换为上一步生成的真实哈希)
```sql
-- 002 seed RBAC: permissions, system roles, role_permissions, initial superadmin (idempotent)

INSERT INTO permissions (code, description) VALUES
  ('dataset:read', '看数据集/版本'),
  ('dataset:write', '建数据集/传版本'),
  ('training:read', '看训练任务'),
  ('training:run', '发起训练'),
  ('model:read', '看模型版本'),
  ('eval:read', '看评估'),
  ('eval:run', '发起评估'),
  ('deploy:read', '看部署'),
  ('deploy:write', '部署/停止'),
  ('user:manage', '用户管理'),
  ('role:manage', '角色管理'),
  ('*', '通配')
ON CONFLICT (code) DO NOTHING;

INSERT INTO roles (name, description, data_scope, is_system) VALUES
  ('superadmin', '超级管理员', 'all', true),
  ('admin', '管理员', 'all', false),
  ('member', '成员', 'own', false),
  ('viewer', '只读', 'own', false)
ON CONFLICT (name) DO NOTHING;

-- superadmin: wildcard
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code = '*'
WHERE r.name = 'superadmin'
ON CONFLICT DO NOTHING;

-- admin + member: business read+write (9 codes)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p
  ON p.code IN ('dataset:read','dataset:write','training:read','training:run',
                'model:read','eval:read','eval:run','deploy:read','deploy:write')
WHERE r.name IN ('admin', 'member')
ON CONFLICT DO NOTHING;

-- viewer: reads (5 codes)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p
  ON p.code IN ('dataset:read','training:read','model:read','eval:read','deploy:read')
WHERE r.name = 'viewer'
ON CONFLICT DO NOTHING;

-- initial superadmin (email admin@modelforge.local, password admin12345 — change after first login)
INSERT INTO users (name, email, password_hash, role_id, is_active)
SELECT 'admin', 'admin@modelforge.local', '<HASH>', r.id, true
FROM roles r WHERE r.name = 'superadmin'
ON CONFLICT (email) DO NOTHING;
```

- [ ] **Step 4: 写端到端测试**(用临时 PG 库跑真实 001+002,验证表/种子/可登录密码)
```python
# services/app-server/tests/test_migrations_apply.py
import bcrypt, psycopg, pytest
from sqlalchemy import create_engine, text
from app.migrate import run_migrations, MIGRATIONS_DIR

PG_ADMIN = "postgresql://modelforge:modelforge@localhost:5432/modelforge"
PG_TEST = "postgresql+psycopg://modelforge:modelforge@localhost:5432/mf_applytest"

@pytest.fixture
def pg_engine():
    admin = psycopg.connect(PG_ADMIN, autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS mf_applytest")
    admin.execute("CREATE DATABASE mf_applytest")
    eng = create_engine(PG_TEST)
    try:
        yield eng
    finally:
        eng.dispose()
        admin.execute("DROP DATABASE IF EXISTS mf_applytest")
        admin.close()

def test_real_migrations_build_schema_and_seed(pg_engine):
    applied = run_migrations(pg_engine, MIGRATIONS_DIR)
    assert "001_init_schema.sql" in applied and "002_seed_rbac.sql" in applied
    with pg_engine.connect() as c:
        ntab = c.execute(text("SELECT count(*) FROM information_schema.tables "
                              "WHERE table_schema='public' AND table_name <> 'schema_migrations'")).scalar()
        nperm = c.execute(text("SELECT count(*) FROM permissions")).scalar()
        nrole = c.execute(text("SELECT count(*) FROM roles")).scalar()
        sa_perms = c.execute(text(
            "SELECT count(*) FROM role_permissions rp "
            "JOIN roles r ON r.id=rp.role_id JOIN permissions p ON p.id=rp.permission_id "
            "WHERE r.name='superadmin' AND p.code='*'")).scalar()
        h = c.execute(text("SELECT password_hash FROM users WHERE email='admin@modelforge.local'")).scalar()
    assert ntab == 10 and nperm == 12 and nrole == 4 and sa_perms == 1
    assert bcrypt.checkpw(b"admin12345", h.encode())
    # 重跑幂等:不再 apply,种子不翻倍
    assert run_migrations(pg_engine, MIGRATIONS_DIR) == []
    with pg_engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM permissions")).scalar() == 12
```

- [ ] **Step 5: 运行确认通过**

Run: `cd services/app-server && python -m pytest tests/test_migrations_apply.py -q`
Expected: PASS(需运行中的 PostgreSQL)。若 `ntab != 10`,说明 001 导出表数不符,检查模型导入。

- [ ] **Step 6: 提交**
```bash
git add services/app-server/db/migrations services/app-server/tests/test_migrations_apply.py
git commit -m "feat(app-server): 001 init schema and 002 RBAC seed migrations"
```

---

### Task 3: 启动自动应用 + conftest 关开关

**Files:**
- Modify: `services/app-server/app/main.py`
- Modify: `services/app-server/tests/conftest.py`
- Test: `services/app-server/tests/test_startup_migrate.py`

- [ ] **Step 1: 写失败测试**(开关关闭时启动不触发迁移)
```python
# services/app-server/tests/test_startup_migrate.py
from fastapi.testclient import TestClient

def test_startup_skips_migration_when_disabled(monkeypatch):
    calls = {"n": 0}
    import app.migrate as mig
    monkeypatch.setattr(mig, "run_migrations", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))
    from app.config import settings
    monkeypatch.setattr(settings, "run_migrations_on_startup", False)
    import app.main as m
    with TestClient(m.app):   # 触发 lifespan startup
        pass
    assert calls["n"] == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services/app-server && python -m pytest tests/test_startup_migrate.py -q`
Expected: FAIL — 当前 `app/main.py` 无 lifespan;但因为还没接线,`run_migrations` 不会被调用,断言 `calls["n"]==0` 可能"假通过"。为确保测试有意义,先在 Step 3 接线后,本测试验证「开关关→不调用」;另在 Step 3 里临时本地手动验证「开关开+PG→调用」。
（若 Step 2 直接通过,说明尚未接线;继续 Step 3 接线,Step 4 复跑确认接线后仍满足"关→不调用"。）

- [ ] **Step 3: 接线 lifespan**
把 `app/main.py` 顶部的 `app = FastAPI(title="ModelForge app-server")` 改为带 lifespan(其余 `include_router` 等保持不变):
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.db import engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.run_migrations_on_startup and engine.dialect.name == "postgresql":
        from app.migrate import run_migrations
        run_migrations(engine)
    yield

app = FastAPI(title="ModelForge app-server", lifespan=lifespan)
```
注意:lifespan 内部 `from app.migrate import run_migrations` 在调用时才 import,使测试的 `monkeypatch.setattr(app.migrate, "run_migrations", ...)` 生效。

- [ ] **Step 4: conftest 关开关**
在 `tests/conftest.py` 顶部(现有 s3 端点修补附近)追加:
```python
from app.config import settings as _settings
_settings.run_migrations_on_startup = False
```
（确保测试里 `TestClient(app)` 触发 lifespan 时不会连真实 PG。）

- [ ] **Step 5: 运行确认通过 + 全套**

Run:
```bash
cd services/app-server && python -m pytest tests/test_startup_migrate.py -q   # PASS(关→不调用)
python -m pytest -q                                                            # 全套绿
```
手动确认「开关开 + PG → 调用」:
```bash
python -c "from app.config import settings; settings.run_migrations_on_startup=True; \
from fastapi.testclient import TestClient; import app.main as m; \
import app.migrate as mig; orig=mig.run_migrations; calls=[]; \
mig.run_migrations=lambda *a,**k: (calls.append(1), [])[1]; \
[None for _ in [TestClient(m.app).__enter__()]]; print('called:', len(calls))"
```
Expected: `called: 1`(说明 PG 路径会触发)。失败也不阻塞——核心是全套测试与关闭路径绿;若该手动片段难跑可跳过并在报告说明。

- [ ] **Step 6: 提交**
```bash
git add services/app-server/app/main.py services/app-server/tests/conftest.py services/app-server/tests/test_startup_migrate.py
git commit -m "feat(app-server): auto-apply migrations on startup (postgres only)"
```

---

### Task 4: 删除 Alembic + 清理 + 文档

**Files:**
- Delete: `services/app-server/alembic/`、`services/app-server/alembic.ini`、`services/app-server/scripts/dump_schema.py`、`services/app-server/db/init.sql`
- Modify: `services/app-server/pyproject.toml`(去掉 alembic 依赖)
- Modify: `CLAUDE.md`(改写 DB 规则)
- Modify: `README.md`(改初始化步骤)

- [ ] **Step 1: 删除 Alembic 与旧产物**
```bash
cd /Users/chenhao/codes/myself/ModelForge
git rm -r services/app-server/alembic
git rm services/app-server/alembic.ini services/app-server/scripts/dump_schema.py services/app-server/db/init.sql
```
在 `services/app-server/pyproject.toml` 的 dependencies 列表删除 `"alembic>=1.13",` 一行。

- [ ] **Step 2: 改写 `CLAUDE.md`**(整体替换文件内容)
```markdown
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

- MLflow 复用同一个 PostgreSQL 库;编号 SQL 只含本项目的表。
- 测试用 SQLite + `Base.metadata.create_all`,不跑编号 SQL(PG 方言);`conftest.py` 已把 `run_migrations_on_startup` 关掉。
```

- [ ] **Step 3: 改 `README.md` 初始化步骤**
把"### 3. 初始化数据库"一节(原来 `alembic upgrade head` + `python -m app.bootstrap`)替换为:
```markdown
### 3. 初始化数据库

迁移在 app 启动时自动应用;也可手动:

\`\`\`bash
cd services/app-server && python -m app.migrate   # 应用 db/migrations/ 下未执行的编号 SQL
\`\`\`

> `001_init_schema.sql` 建表、`002_seed_rbac.sql` 写种子(权限/角色/初始超管)。初始超管 `admin@modelforge.local` / `admin12345`(**首登后请改**)。生产环境务必用 env 覆盖 `JWT_SECRET`、`INTERNAL_TOKEN`、MinIO 凭证等默认值。**所有业务端点都需登录**。
```
并把 README 里其它提到 `alembic upgrade head` / `python -m app.bootstrap` / `db/init.sql` 的地方一并改为编号 SQL 迁移的说法(若有)。

- [ ] **Step 4: 验证**
```bash
cd /Users/chenhao/codes/myself/ModelForge/services/app-server
python -m pytest -q                 # 全套绿(无测试依赖 alembic)
python -m app.migrate               # 对现有 dev PG 幂等应用(001 空操作、002 补种子);打印 applied
grep -rn "alembic" . --include=*.py --include=*.ini --include=*.toml || echo "no alembic refs left"
```
Expected: 全套测试 PASS;`python -m app.migrate` 正常打印 applied(首次可能含 001/002,再跑 `(none)`);无残留 alembic 引用。

- [ ] **Step 5: 提交**
```bash
cd /Users/chenhao/codes/myself/ModelForge
git add -A
git commit -m "refactor(app-server): remove Alembic in favor of numbered SQL migrations; update docs"
```

---

## 自查(Self-Review)

**Spec 覆盖:**
- §2/§3 runner + schema_migrations → Task 1 ✅
- §2 001/002 文件 → Task 2 ✅
- §4 启动自动应用(PG + 开关)→ Task 3 ✅
- §5 测试影响(conftest 关开关、新增 test_migrate)→ Task 1/2/3 ✅
- §6 种子做成 SQL + bootstrap 留作测试 → Task 2(SQL);bootstrap.py 不动 ✅
- §7 幂等过渡(IF NOT EXISTS/ON CONFLICT)→ Task 2 文件写法 + Task 4 对现有库实跑 ✅
- §2/§8 删除 alembic + dump_schema + init.sql + 改 CLAUDE.md/README → Task 4 ✅

**占位符扫描:** `002_seed_rbac.sql` 的 `<HASH>` 是 Task 2 Step 2 生成的真实 bcrypt 串(明确的生成步骤,非遗留占位);其余每步含完整代码。无 TBD。

**类型一致性:** `run_migrations(eng=engine, migrations_dir=MIGRATIONS_DIR) -> list[str]` 在 Task 1 定义,Task 2 测试与 Task 3 lifespan 调用一致;`MIGRATIONS_DIR` 从 Task 1 导出,Task 2 测试引用;`settings.run_migrations_on_startup` 在 Task 1 定义、Task 3 lifespan/conftest 使用。

**风险/前置:** Task 1/2 的测试需要运行中的 PostgreSQL(建/删临时库);CI 无 PG 时这两个文件会失败——dev 环境有 PG,本计划默认在 dev 跑。其余测试仍 SQLite 无需 PG。
