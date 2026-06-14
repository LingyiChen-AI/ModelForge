from fastapi.testclient import TestClient

def test_startup_skips_migration_when_disabled(monkeypatch):
    calls = {"n": 0}
    import app.migrate as mig
    monkeypatch.setattr(mig, "run_migrations", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))
    from app.config import settings
    monkeypatch.setattr(settings, "run_migrations_on_startup", False)
    import app.main as m
    with TestClient(m.app):   # triggers lifespan startup
        pass
    assert calls["n"] == 0
