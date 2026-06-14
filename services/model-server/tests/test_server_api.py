from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from modelforge_common.apikey import hash_key
import server.api_auth as api_auth


def _patch_key(monkeypatch, tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/k.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE api_keys (key_hash TEXT, scopes TEXT, revoked_at TIMESTAMP)"))
        c.execute(text("INSERT INTO api_keys VALUES (:h, '[\"inference\"]', NULL)"),
                  {"h": hash_key("good")})
    monkeypatch.setattr(api_auth, "_get_engine", lambda: eng)


def test_predict_requires_api_key():
    from server.main import app
    c = TestClient(app)
    r = c.post("/predict", json={"model_version_id": 1, "texts": ["x"]})
    assert r.status_code == 401 and r.json()["code"] == 401


def test_load_predict_unload(monkeypatch, tmp_path):
    import server.store as st
    import server.main as m

    _patch_key(monkeypatch, tmp_path)

    class FakePred:
        def predict(self, texts):
            return [{"label": "pos", "score": 0.9} for _ in texts]

    monkeypatch.setattr(st, "download_model", lambda name, version: "/tmp/x")
    monkeypatch.setattr(st, "build_predictor", lambda task_type, model_dir: FakePred())

    c = TestClient(m.app)
    r = c.post("/load", json={"model_version_id": 5, "mlflow_model_name": "ModelForge-j",
                              "mlflow_version": "1", "task_type": "classification"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0 and body["data"]["loaded"] is True

    r = c.post("/predict", json={"model_version_id": 5, "texts": ["hi", "yo"]},
               headers={"X-Api-Key": "good"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0 and len(body["data"]["predictions"]) == 2

    assert 5 in c.get("/loaded").json()["data"]["model_version_ids"]
    assert c.request("DELETE", "/loaded/5").status_code == 200
    assert 5 not in c.get("/loaded").json()["data"]["model_version_ids"]


def test_predict_not_loaded(monkeypatch, tmp_path):
    import server.main as m
    _patch_key(monkeypatch, tmp_path)
    c = TestClient(m.app)
    r = c.post("/predict", json={"model_version_id": 999, "texts": ["x"]},
               headers={"X-Api-Key": "good"})
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == 404 and body["data"] is None and "not loaded" in body["message"]
