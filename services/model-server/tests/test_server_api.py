from fastapi.testclient import TestClient


def test_load_predict_unload(monkeypatch):
    import server.store as st
    import server.main as m

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

    r = c.post("/predict", json={"model_version_id": 5, "texts": ["hi", "yo"]})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0 and len(body["data"]["predictions"]) == 2

    assert 5 in c.get("/loaded").json()["data"]["model_version_ids"]
    assert c.request("DELETE", "/loaded/5").status_code == 200
    assert 5 not in c.get("/loaded").json()["data"]["model_version_ids"]


def test_predict_not_loaded():
    import server.main as m
    c = TestClient(m.app)
    r = c.post("/predict", json={"model_version_id": 999, "texts": ["x"]})
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == 404 and body["data"] is None and "not loaded" in body["message"]
