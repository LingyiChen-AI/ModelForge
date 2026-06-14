from fastapi.testclient import TestClient


def test_model_trainings_timeline(session_factory):
    from app import db as dbmod
    S = session_factory  # fixture creates tables + sets app.db.SessionLocal
    db = S()
    from app.models.training import Model, TrainingJob, ModelVersion
    from app.models.dataset import Dataset, DatasetVersion
    train = Dataset(name="分类-训练集", kind="train", task_type="classification")
    ev = Dataset(name="分类-评估集", kind="eval", task_type="classification")
    db.add_all([train, ev]); db.commit()
    tv1 = DatasetVersion(dataset_id=train.id, version_no=1, storage_uri="s3://a", row_count=10, checksum="a", note="")
    tv2 = DatasetVersion(dataset_id=train.id, version_no=2, storage_uri="s3://b", row_count=20, checksum="b", note="")
    evv = DatasetVersion(dataset_id=ev.id, version_no=1, storage_uri="s3://c", row_count=5, checksum="c", note="")
    db.add_all([tv1, tv2, evv]); db.commit()
    m = Model(name="m", task_type="classification"); db.add(m); db.commit()
    job = TrainingJob(name="20260101", model_id=m.id, dataset_version_id=tv1.id,
                      dataset_version_ids=[tv1.id, tv2.id], eval_dataset_version_id=evv.id,
                      eval_dataset_version_ids=[evv.id], base_model="b", task_type="classification",
                      hyperparams={}, status="succeeded")
    db.add(job); db.commit()
    mv = ModelVersion(name="m", model_id=m.id, source_training_job_id=job.id,
                      mlflow_model_name="m", mlflow_version="1", task_type="classification",
                      base_model="b", train_metrics={"accuracy": 0.97, "f1": 0.96})
    db.add(mv); db.commit()
    mid = m.id; db.close()

    from tests.conftest import make_user, auth_headers
    d = dbmod.SessionLocal(); u = make_user(d, codes=("*",), data_scope="all", email="mt@x.com"); d.close()
    H = auth_headers(u.id)
    from app.main import app
    c = TestClient(app)

    r = c.get(f"/models/{mid}/trainings", headers=H)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    rec = rows[0]
    assert rec["train_count"] == 2 and rec["eval_count"] == 1
    assert rec["train_datasets"] == ["分类-训练集 V1", "分类-训练集 V2"]
    assert rec["eval_datasets"] == ["分类-评估集 V1"]
    assert rec["version_label"] == "1" and rec["metrics"]["accuracy"] == 0.97
    assert rec["status"] == "succeeded" and rec["created_by_name"] is None
    # unknown model -> 404
    assert c.get("/models/999999/trainings", headers=H).status_code == 404
