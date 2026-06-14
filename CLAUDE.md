# ModelForge — 项目约定

## 数据库 schema 与 SQL 初始化文件

- 权威 schema 来源 = `services/app-server` 的 SQLAlchemy 模型(`app/models/`),变更通过 Alembic 迁移落库。
- **`services/app-server/db/init.sql`** 是从模型导出的完整建表 DDL(PostgreSQL),供从零初始化数据库使用。它是**自动生成**的,不要手改。
- 生成/再生成命令:
  ```bash
  cd services/app-server && python scripts/dump_schema.py
  ```
  脚本无需数据库连接(把 ORM metadata 编译成 DDL),按外键依赖顺序输出。

### 铁律:schema 变更必须同步 init.sql

**任何改动数据库结构后(改 `app/models/` 模型、加/改 Alembic 迁移、新增表或列),必须在同一次提交里重新生成 `db/init.sql`:**

```bash
cd services/app-server && python scripts/dump_schema.py
git add db/init.sql
```

否则 `init.sql` 会与模型/迁移漂移。判断标准:`git diff` 里只要动了 `app/models/**` 或 `alembic/versions/**`,就必须同时包含 `db/init.sql` 的更新。

- `init.sql` 只含 schema。种子数据(权限目录 / 系统角色 / 初始超管)由 `python -m app.bootstrap` 写入,**不**进 init.sql。
- 注意 MLflow 复用同一个 PostgreSQL 库;`alembic/env.py` 的 `include_object` 过滤只让 autogenerate 处理本项目的表,`init.sql` 也只含本项目的表。
