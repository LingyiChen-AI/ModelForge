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
    assert ntab == 11 and nperm == 13 and nrole == 4 and sa_perms == 1
    assert bcrypt.checkpw(b"admin12345", h.encode())
    assert run_migrations(pg_engine, MIGRATIONS_DIR) == []
    with pg_engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM permissions")).scalar() == 13
