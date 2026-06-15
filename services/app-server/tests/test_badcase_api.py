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


def test_badcase_out_includes_fixed_by():
    from datetime import datetime
    from app.schemas.badcase import BadcaseOut
    out = BadcaseOut(id=1, model_version_id=1, task_type="classification",
                     input={"text": "a"}, inference={}, category=None, source=None,
                     source_ref=None, status="reported", annotation=None,
                     dataset_version_id=None, created_at=datetime(2026, 6, 15))
    assert out.fixed_by == []


def test_badcase_summary_counts(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.training import TrainingJob, ModelVersion
    from app.models.badcase import Badcase
    eng = create_engine(f"sqlite:///{tmp_path}/s.db"); Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False); db = S()
    job = TrainingJob(name="j", dataset_version_id=1, base_model="b",
                      task_type="classification", hyperparams={}); db.add(job); db.commit()
    mv = ModelVersion(name="意图", source_training_job_id=job.id, mlflow_model_name="意图",
                      mlflow_version="3", task_type="classification", base_model="b", train_metrics={})
    db.add(mv); db.commit()
    db.add_all([
        Badcase(model_version_id=mv.id, task_type="classification", input={"text":"a"}, status="reported"),
        Badcase(model_version_id=mv.id, task_type="classification", input={"text":"b"}, status="annotated", annotation={"label":"x"}),
        Badcase(model_version_id=mv.id, task_type="classification", input={"text":"c"}, status="used",
                annotation={"label":"y"}, fixed_by=[{"model_version_id": 99, "version_label": "4"}]),
    ]); db.commit()
    from app.services.badcase_service import summary
    rows = summary(db)
    assert len(rows) == 1
    r = rows[0]
    assert r["model_version_id"] == mv.id and r["model_name"] == "意图" and r["model_version_label"] == "3"
    assert r["reported"] == 3 and r["annotated"] == 2 and r["used"] == 1
    assert r["pending"] == 1 and r["fixed"] == 1
    assert r["fixed_versions"] == ["4"]


def test_mark_fixed_appends_and_dedupes(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.badcase import Badcase
    eng = create_engine(f"sqlite:///{tmp_path}/f.db"); Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False); db = S()
    b = Badcase(model_version_id=1, task_type="classification", input={"text":"a"},
                status="used", annotation={"label":"x"}); db.add(b); db.commit()
    from app.services.badcase_service import mark_fixed
    mark_fixed(db, [b.id], model_version_id=5, version_label="4")
    db.refresh(b)
    assert len(b.fixed_by) == 1 and b.fixed_by[0]["model_version_id"] == 5 and b.fixed_by[0]["version_label"] == "4"
    mark_fixed(db, [b.id], model_version_id=5, version_label="4")
    db.refresh(b)
    assert len(b.fixed_by) == 1
    mark_fixed(db, [b.id], model_version_id=8, version_label="7")
    db.refresh(b)
    assert len(b.fixed_by) == 2 and b.fixed_by[1]["version_label"] == "7"


def test_report_result_marks_badcases_fixed(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.training import TrainingJob
    from app.models.badcase import Badcase
    from app.services.mlflow_sync import upsert_model_version_from_result
    from app.services.badcase_service import mark_fixed
    eng = create_engine(f"sqlite:///{tmp_path}/r.db"); Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False); db = S()
    job = TrainingJob(name="j", dataset_version_id=1, base_model="b",
                      task_type="classification", hyperparams={}); db.add(job); db.commit()
    b = Badcase(model_version_id=1, task_type="classification", input={"text":"a"},
                status="used", annotation={"label":"x"}); db.add(b); db.commit()
    mv = upsert_model_version_from_result(db, job.id, {
        "model_name": "意图", "version": "4", "metrics": {"accuracy": 0.9, "badcase_fix_rate": 0.5}})
    mark_fixed(db, [b.id], model_version_id=mv.id, version_label=mv.mlflow_version)
    db.refresh(b)
    assert b.fixed_by[0]["version_label"] == "4"
    assert mv.train_metrics["badcase_fix_rate"] == 0.5


def test_report_result_endpoint_marks_fixed(session_factory):
    """POST /training-jobs/internal/{job_id}/result with badcase_fixes wires the
    real endpoint function, verifying the if body.badcase_fixes: branch is exercised."""
    from app import db as dbmod
    from app.models.training import TrainingJob
    from app.models.badcase import Badcase
    db = session_factory()
    job = TrainingJob(name="j", dataset_version_id=1, base_model="b",
                      task_type="classification", hyperparams={})
    db.add(job); db.commit()
    b = Badcase(model_version_id=1, task_type="classification", input={"text": "test"},
                status="used", annotation={"label": "A"})
    db.add(b); db.commit()
    jid = job.id; bid = b.id; db.close()

    from app.main import app
    from app.auth import require_internal_token
    app.dependency_overrides[require_internal_token] = lambda: None
    try:
        from fastapi.testclient import TestClient
        c = TestClient(app)
        r = c.post(f"/training-jobs/internal/{jid}/result", json={
            "run_id": "run-abc", "model_name": "意图", "version": "5",
            "metrics": {"accuracy": 0.95}, "badcase_fixes": [bid],
        })
        assert r.status_code == 201, r.text
        mv_id = r.json()["model_version_id"]
        # confirm badcase.fixed_by was updated in the DB
        db2 = dbmod.SessionLocal()
        bc = db2.get(Badcase, bid); db2.refresh(bc)
        assert len(bc.fixed_by) == 1
        assert bc.fixed_by[0]["version_label"] == "5"
        assert bc.fixed_by[0]["model_version_id"] == mv_id
        db2.close()
    finally:
        app.dependency_overrides.pop(require_internal_token, None)


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
