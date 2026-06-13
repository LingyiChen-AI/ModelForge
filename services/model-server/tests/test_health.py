from fastapi.testclient import TestClient
from server.main import app


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}
