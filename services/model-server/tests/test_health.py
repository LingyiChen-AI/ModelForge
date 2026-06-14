from fastapi.testclient import TestClient
from server.main import app


def test_health():
    assert TestClient(app).get("/health").json() == {"code": 0, "data": {"status": "ok"}, "message": "success"}
