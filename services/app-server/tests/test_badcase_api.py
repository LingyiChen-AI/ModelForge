def test_badcase_model_roundtrip(session_factory):
    from app.models.badcase import Badcase
    db = session_factory()
    b = Badcase(model_version_id=1, task_type="classification",
                input={"text": "x"}, inference={"label": "A", "score": 0.9},
                category="A", source="svc", status="reported")
    db.add(b); db.commit(); db.refresh(b)
    assert b.id and b.status == "reported" and b.annotation is None


from fastapi.testclient import TestClient

def _setup_version(session_factory):
    from app import db as dbmod
    db = session_factory()
    from app.models.training import Model, TrainingJob, ModelVersion
    m = Model(name="客服分类", task_type="classification"); db.add(m); db.commit()
    job = TrainingJob(name="j", dataset_version_id=1, base_model="b", task_type="classification", hyperparams={}, model_id=m.id)
    db.add(job); db.commit()
    mv = ModelVersion(name="客服分类", model_id=m.id, source_training_job_id=job.id,
                      mlflow_model_name="客服分类", mlflow_version="1", task_type="classification",
                      base_model="b", train_metrics={})
    db.add(mv); db.commit()
    mvid = mv.id; db.close()
    return mvid

def test_report_badcase_with_api_key(session_factory, monkeypatch):
    mvid = _setup_version(session_factory)
    from app.services import api_key_service
    from app import db as dbmod
    db = dbmod.SessionLocal()
    plaintext, _ = api_key_service.create_key(db, name="svc", scopes=["badcase:report"], created_by=None)
    db.close()
    from app.main import app
    c = TestClient(app)
    r = c.post("/badcase/report", headers={"X-Api-Key": plaintext},
               json={"model_version_id": mvid, "input": {"text": "怎么退货"},
                     "inference": {"label": "物流查询", "score": 0.8}, "source_ref": "ext-1"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "reported" and r.json()["category"] == "物流查询"
    # idempotent on (source, source_ref)
    r2 = c.post("/badcase/report", headers={"X-Api-Key": plaintext},
                json={"model_version_id": mvid, "input": {"text": "怎么退货"},
                      "inference": {"label": "物流查询"}, "source_ref": "ext-1"})
    assert r2.json()["id"] == r.json()["id"]
    # bad input -> 422
    assert c.post("/badcase/report", headers={"X-Api-Key": plaintext},
                  json={"model_version_id": mvid, "input": {"nope": 1}, "inference": {}}).status_code == 422
    # missing/invalid key -> 401
    assert c.post("/badcase/report", json={"model_version_id": mvid, "input": {"text": "x"}, "inference": {}}).status_code == 401
    # unknown version -> 422
    assert c.post("/badcase/report", headers={"X-Api-Key": plaintext},
                  json={"model_version_id": 99999, "input": {"text": "x"}, "inference": {}}).status_code == 422


def test_annotate_missing_and_ok(session_factory, monkeypatch):
    mvid = _setup_version(session_factory)
    from app import db as dbmod
    from app.models.badcase import Badcase
    d = dbmod.SessionLocal()
    bcase = Badcase(model_version_id=mvid, task_type="classification",
                    input={"text": "x"}, inference={"label": "A"}, status="reported")
    d.add(bcase); d.commit(); cid = bcase.id; d.close()
    from tests.conftest import make_user, auth_headers
    d = dbmod.SessionLocal(); u = make_user(d, codes=("*",), data_scope="all", email="anno@x.com"); d.close()
    H = auth_headers(u.id)
    from app.main import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    # missing case -> 404
    assert c.patch("/badcases/999999/annotate", json={"annotation": {"label": "B"}}, headers=H).status_code == 404
    # ok -> 200, status annotated
    r = c.patch(f"/badcases/{cid}/annotate", json={"annotation": {"label": "售后服务"}}, headers=H)
    assert r.status_code == 200 and r.json()["status"] == "annotated" and r.json()["annotation"] == {"label": "售后服务"}
    # invalid annotation (missing required key) -> 422
    assert c.patch(f"/badcases/{cid}/annotate", json={"annotation": {"nope": 1}}, headers=H).status_code == 422
