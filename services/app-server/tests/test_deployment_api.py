from fastapi.testclient import TestClient

def test_create_and_stop_deployment(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.training import TrainingJob, ModelVersion
    eng = create_engine(f"sqlite:///{tmp_path}/t.db"); Base.metadata.create_all(eng)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    s = dbmod.SessionLocal()
    job = TrainingJob(name="j", dataset_version_id=1, base_model="b",
                      task_type="classification", hyperparams={}); s.add(job); s.commit()
    mv = ModelVersion(name="ModelForge-j", source_training_job_id=job.id,
                      mlflow_model_name="ModelForge-j", mlflow_version="1",
                      task_type="classification", base_model="b", train_metrics={})
    s.add(mv); s.commit(); mv_id = mv.id; s.close()

    import app.services.deployment_service as ds
    calls = {}
    monkeypatch.setattr(ds, "notify_load", lambda mv: calls.setdefault("load", mv.id))
    monkeypatch.setattr(ds, "notify_unload", lambda mvid: calls.setdefault("unload", mvid))

    from app.main import app
    c = TestClient(app)
    r = c.post("/deployments", json={"model_version_id": mv_id})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "running" and calls["load"] == mv_id

    r = c.post(f"/deployments/{body['id']}/stop")
    assert r.status_code == 200 and r.json()["status"] == "stopped"
    assert calls["unload"] == mv_id
