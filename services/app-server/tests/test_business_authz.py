from fastapi.testclient import TestClient
from tests.conftest import make_user, auth_headers

def _seed_mv(db, owner_id):
    from app.models.dataset import Dataset, DatasetVersion
    from app.models.training import TrainingJob, ModelVersion
    ds = Dataset(name="d", kind="train", task_type="classification", created_by=owner_id)
    db.add(ds); db.commit()
    dv = DatasetVersion(dataset_id=ds.id, version_no=1, storage_uri="s3://x/y",
                        row_count=2, checksum="c", note=""); db.add(dv); db.commit()
    job = TrainingJob(name="j", dataset_version_id=dv.id, base_model="b",
                      task_type="classification", hyperparams={}, created_by=owner_id)
    db.add(job); db.commit()
    mv = ModelVersion(name="m", source_training_job_id=job.id, mlflow_model_name="m",
                      mlflow_version="1", task_type="classification", base_model="b",
                      train_metrics={}, created_by=owner_id); db.add(mv); db.commit()
    return dv.id, mv.id

def test_training_requires_run_and_scope(session_factory):
    S = session_factory; db = S()
    a = make_user(db, codes=("training:read","training:run"), data_scope="own", email="a@x.com")
    b = make_user(db, codes=("training:read",), data_scope="own", email="b@x.com")
    dv_id, _ = _seed_mv(db, a.id)
    aid, bid = a.id, b.id; db.close()
    from app.main import app
    c = TestClient(app)
    assert c.post("/training-jobs", json={"name":"j2","dataset_version_id":dv_id,
        "base_model":"b","task_type":"classification","hyperparams":{}},
        headers=auth_headers(bid)).status_code == 403
    assert c.get("/training-jobs", headers=auth_headers(bid)).json() == []

def test_model_versions_scope(session_factory):
    S = session_factory; db = S()
    a = make_user(db, codes=("model:read",), data_scope="own", email="a2@x.com")
    b = make_user(db, codes=("model:read",), data_scope="own", email="b2@x.com")
    _seed_mv(db, a.id)
    aid, bid = a.id, b.id; db.close()
    from app.main import app
    c = TestClient(app)
    assert len(c.get("/model-versions", headers=auth_headers(aid)).json()) == 1
    assert c.get("/model-versions", headers=auth_headers(bid)).json() == []
