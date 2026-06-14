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
