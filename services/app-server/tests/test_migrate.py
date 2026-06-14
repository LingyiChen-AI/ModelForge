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
    (tmp_path / "001_a.sql").write_text(
        "CREATE TABLE IF NOT EXISTS t_a (id INT PRIMARY KEY);\n"
        "CREATE TABLE IF NOT EXISTS t_a2 (id INT PRIMARY KEY);")
    (tmp_path / "002_b.sql").write_text(
        "CREATE TABLE IF NOT EXISTS t_b (id INT PRIMARY KEY);")
    from app.migrate import run_migrations
    assert run_migrations(pg_engine, tmp_path) == ["001_a.sql", "002_b.sql"]
    assert run_migrations(pg_engine, tmp_path) == []
    with pg_engine.connect() as c:
        versions = {r[0] for r in c.execute(text("SELECT version FROM schema_migrations"))}
        ntables = c.execute(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name IN ('t_a','t_a2','t_b')")).scalar()
    assert versions == {"001_a.sql", "002_b.sql"}
    assert ntables == 3
