"""Dump the full app-server schema (from SQLAlchemy models) to db/init.sql.

This emits PostgreSQL `CREATE TABLE` DDL for every table registered on
`Base.metadata`, in foreign-key dependency order. It needs NO database
connection — it compiles the ORM metadata to DDL text.

Run after ANY schema change (new/edited model or Alembic migration):

    cd services/app-server && python scripts/dump_schema.py

The generated db/init.sql is schema-only. Seed data (permissions / system
roles / initial superadmin) is applied separately via `python -m app.bootstrap`.
"""

from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models import Base
import app.models  # noqa: F401  ensure every model module registers its tables

OUTPUT = Path(__file__).resolve().parent.parent / "db" / "init.sql"

HEADER = """\
-- ModelForge app-server schema (PostgreSQL)
-- AUTO-GENERATED from SQLAlchemy models by scripts/dump_schema.py — do not edit by hand.
-- Regenerate after any schema change:  cd services/app-server && python scripts/dump_schema.py
-- Schema only. Seed data: python -m app.bootstrap
"""


def render() -> str:
    dialect = postgresql.dialect()
    blocks = [HEADER]
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect)).strip()
        blocks.append(f"{ddl};")
    return "\n\n".join(blocks) + "\n"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render())
    print(f"wrote {OUTPUT} ({len(Base.metadata.sorted_tables)} tables)")


if __name__ == "__main__":
    main()
