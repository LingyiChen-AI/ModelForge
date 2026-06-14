from fastapi.testclient import TestClient

def test_create_eval_run(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    from app.models.dataset import Dataset, DatasetVersion
    from app.models.training import TrainingJob, ModelVersion
    eng = create_engine(f"sqlite:///{tmp_path}/t.db"); Base.metadata.create_all(eng)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    s = dbmod.SessionLocal()
    ds = Dataset(name="e", kind="eval", task_type="classification"); s.add(ds); s.commit()
    dv = DatasetVersion(dataset_id=ds.id, version_no=1, storage_uri="s3://x/y",
                        row_count=4, checksum="c", note=""); s.add(dv); s.commit()
    job = TrainingJob(name="j", dataset_version_id=dv.id, base_model="bert-base",
                      task_type="classification", hyperparams={}); s.add(job); s.commit()
    mv = ModelVersion(name="ModelForge-j", source_training_job_id=job.id,
                      mlflow_model_name="ModelForge-j", mlflow_version="1",
                      task_type="classification", base_model="bert-base", train_metrics={})
    s.add(mv); s.commit()
    mv_id, dv_id = mv.id, dv.id; s.close()

    from tests.conftest import make_user, auth_headers
    _d = dbmod.SessionLocal(); _root = make_user(_d, codes=("*",), data_scope="all", email="root_eval@x.com")
    H = auth_headers(_root.id); _d.close()

    import app.services.eval_service as es
    sent = {}
    def fake_send(run_id):
        sent["run"] = run_id
        return "celery-eval-1"
    monkeypatch.setattr(es, "send_eval_task", fake_send)

    from app.main import app
    c = TestClient(app)
    r = c.post("/eval-runs", json={"model_version_id": mv_id, "dataset_version_id": dv_id}, headers=H)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending" and body["celery_task_id"] == "celery-eval-1"
    assert sent["run"] == body["id"]

    # delete the eval run
    run_id = body["id"]
    rd = c.delete(f"/eval-runs/{run_id}", headers=H)
    assert rd.status_code == 204
    assert c.get(f"/eval-runs/{run_id}", headers=H).status_code == 404
