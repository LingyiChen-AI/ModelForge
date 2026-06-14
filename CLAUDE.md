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
