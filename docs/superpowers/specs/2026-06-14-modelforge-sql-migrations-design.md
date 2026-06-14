# ModelForge SQL 迁移(替换 Alembic)设计文档

- 日期:2026-06-14
- 状态:已评审,待实现计划
- 范围:用「编号 SQL 迁移文件 + 自建 runner + 启动自动应用」替换 Alembic

## 1. 背景与目标

当前 app-server 用 Alembic 管理 schema(`alembic/` + 8 个 versions),并有一份从模型导出的 `db/init.sql`。改为更直白的方案:

- 一个 `db/migrations/` 目录,放**按编号顺序**的 `.sql` 文件(`001_*.sql`、`002_*.sql`…)。
- 一个**自建轻量 runner**,用 `schema_migrations` 表记录已执行的文件,按编号只跑没跑过的。
- app-server **启动时自动**应用未执行的迁移。
- **整体删除 Alembic**。

### 关键决策

1. 执行/跟踪 = **自建 Python runner** + `schema_migrations` 表(不引入 dbmate 等外部工具)。
2. **删除** `alembic/`、`alembic.ini`、`alembic` 依赖,以及 `scripts/dump_schema.py` 和 `db/init.sql`。
3. **源真相仍是 SQLAlchemy 模型**(app 查询要用);编号 SQL 是部署/历史载体。**改模型时,同次提交里新增一个对应的编号 SQL**(`CREATE`/`ALTER`),由 runner 启动时自动应用。无 autogenerate,靠 CLAUDE.md 纪律保证模型与 SQL 一致。
4. 种子数据(权限目录/系统角色/初始超管)做成编号 SQL(`002_seed_rbac.sql`),幂等 `INSERT ... ON CONFLICT DO NOTHING`,admin 密码 bcrypt 哈希**预先算好写死**。
5. 迁移文件用**幂等 DDL/DML**(`CREATE TABLE IF NOT EXISTS` / `ON CONFLICT DO NOTHING`),因此对**现有已建好的库重跑也无害**,自然完成从 Alembic 的过渡,不单独做 baseline。
6. 启动自动应用**仅当连 PostgreSQL 且开关开启**;测试用 SQLite + ORM,不触发。

### 非目标

- 不做 down/回滚(编号 SQL 只前进;需回退就再写一个补偿迁移)。
- 不引入外部迁移工具/二进制。

## 2. 目录与文件

```
services/app-server/
  db/migrations/
    001_init_schema.sql    # 全量建表(CREATE TABLE IF NOT EXISTS),= 现 db/init.sql 内容
    002_seed_rbac.sql      # 12 权限 + 4 系统角色 + role_permissions + 初始超管(幂等)
    003_*.sql              # 以后每次 schema/种子变更新增一个编号文件
  app/migrate.py           # runner
  app/main.py              # 启动 lifespan 调 run_migrations
  app/config.py            # 增 run_migrations_on_startup
```
删除:`alembic/`、`alembic.ini`、`scripts/dump_schema.py`、`db/init.sql`;`pyproject.toml` 去掉 `alembic`。

## 3. 迁移 runner(`app/migrate.py`)

```python
from pathlib import Path
from app.db import engine

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"

def run_migrations(eng=engine) -> list[str]:
    with eng.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT now())")
        done = {r[0] for r in conn.exec_driver_sql("SELECT version FROM schema_migrations")}
    applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in done:
            continue
        sql = path.read_text()
        with eng.begin() as conn:
            conn.exec_driver_sql(sql)                       # 整个文件可多语句,一个事务
            conn.exec_driver_sql(
                "INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
        applied.append(path.name)
    return applied

def run():  # python -m app.migrate
    applied = run_migrations()
    print(f"applied: {applied or '(none)'}")

if __name__ == "__main__":
    run()
```

- 每个文件在**独立事务**内执行(原子);记录用 `path.name`(如 `001_init_schema.sql`)。
- `exec_driver_sql` 走 psycopg,支持一次执行多语句的 SQL 文本。
- 命令行入口:`python -m app.migrate`。

## 4. 启动自动应用(`app/main.py`)

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
# ... 现有 include_router 不变
```
`app/config.py` Settings 增:`run_migrations_on_startup: bool = True`。

## 5. 测试影响

- 业务/RBAC 测试用 SQLite + `Base.metadata.create_all` + `bootstrap.seed`,**完全不变**(编号 SQL 是 PG 方言,不用于 SQLite 测试)。
- `tests/conftest.py` 顶部追加 `settings.run_migrations_on_startup = False`,这样 `TestClient(app)` 触发 lifespan 时不会去碰真实 PG。
- 新增 `tests/test_migrate.py`:连一个临时 PG 库验证 runner —— 首跑应用 `001`+`002`、重跑应用 0 个(幂等)、`schema_migrations` 记录正确。

## 6. 种子数据

- `002_seed_rbac.sql` 是**生产种子的唯一路径**(随迁移自动跑):
  - 12 条 `permissions`(`INSERT ... ON CONFLICT (code) DO NOTHING`)。
  - 4 个系统角色(`ON CONFLICT (name) DO NOTHING`):`superadmin`(all, is_system) / `admin`(all) / `member`(own) / `viewer`(own)。
  - `role_permissions`:用 `INSERT ... SELECT ... ON CONFLICT DO NOTHING` 按 code 集合关联(superadmin=`*`;admin/member=业务读写 9 项;viewer=5 个 `*:read`)。
  - 初始超管 `users`:`INSERT ... SELECT ... ON CONFLICT (email) DO NOTHING`,密码哈希写死(对应 `admin12345`,**首登后请改**)。
- `app/bootstrap.py` **保留**,仅作**测试用程序化 seed**(SQLite 上 `bootstrap.seed(db)`,登录测试需动态哈希)。它与 `002_seed_rbac.sql` 必须列**同一份**权限目录/角色/关联(CLAUDE.md 提醒)。
- README 去掉 `python -m app.bootstrap` 步骤(生产种子改由迁移自动应用;也可 `python -m app.migrate` 手动触发)。

## 7. 从 Alembic 过渡

- 现有 dev 库已有全部表(经 Alembic)。首次 runner 运行:建 `schema_migrations` → 跑 `001`(`IF NOT EXISTS`,空操作)→ 跑 `002`(按需补种子)→ 记录两条。无需手动 baseline。
- 残留的 `alembic_version` 表无害;可手动 `DROP TABLE alembic_version`(文档注明,非必须)。

## 8. CLAUDE.md 规则改写

替换原「重生成 init.sql」规则为:

> **数据库变更铁律**:改 `app/models/**`(加表/列/约束)时,**同次提交**里必须在 `services/app-server/db/migrations/` 新增一个**下一个编号**的 `.sql` 文件,写对应的 `CREATE`/`ALTER`(幂等:`IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` / `ON CONFLICT DO NOTHING`)。种子变更同样新增编号 SQL。runner 在 app 启动时(PostgreSQL)自动应用,或 `python -m app.migrate`。判断标准:`git diff` 动了 `app/models/**` 就必须同时新增/包含一个 `db/migrations/NNN_*.sql`。不要再用 Alembic。
>
> 测试用的程序化 seed(`app/bootstrap.py`)需与 `002_seed_rbac.sql` 的权限目录/角色保持一致。

## 9. 实现分阶段(供拆 plan)

1. runner + config 开关 + `tests/test_migrate.py`(临时 PG 库验证幂等)。
2. 生成 `001_init_schema.sql`(从当前模型导出 DDL,改 `IF NOT EXISTS`)与 `002_seed_rbac.sql`(手写幂等种子 + 预算哈希);用临时 PG 库实跑验证两文件 + runner。
3. `main.py` 启动 lifespan 接线;conftest 关开关;全套测试绿。
4. 删除 Alembic(`alembic/`、`alembic.ini`、pyproject 依赖)、`scripts/dump_schema.py`、`db/init.sql`;改写 CLAUDE.md;改 README。

## 10. 风险/影响

- 失去 autogenerate:模型与编号 SQL 的一致性靠人工纪律(CLAUDE.md)。可在 CI 加一个「用 001+全部迁移建库 vs `Base.metadata` 比对」的校验作为后续增强(本设计不含)。
- 种子密码哈希写死:改 `seed_admin_password` 不影响已写死的 SQL;以首登改密或新增编号 SQL 解决。
- 启动自动迁移:仅 PG + 开关;多实例并发启动时多个进程可能同时跑——单文件事务 + `IF NOT EXISTS`/`ON CONFLICT` 使其幂等安全,但同一文件可能被两个进程都尝试(其一 `INSERT schema_migrations` 撞主键失败回滚,DDL 因幂等无副作用)。小团队单实例场景足够;大规模可后续加 advisory lock。
