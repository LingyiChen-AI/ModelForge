from unittest.mock import MagicMock
from fastapi.testclient import TestClient

def test_create_training_job(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    eng = create_engine(f"sqlite:///{tmp_path}/t.db"); Base.metadata.create_all(eng)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    # 准备一个 dataset_version
    from app.models.dataset import Dataset, DatasetVersion
    s = dbmod.SessionLocal()
    ds = Dataset(name="d", kind="train", task_type="classification"); s.add(ds); s.commit()
    dv = DatasetVersion(dataset_id=ds.id, version_no=1, storage_uri="s3://x/y",
                        row_count=2, checksum="c", note=""); s.add(dv); s.commit()
    dv_id = dv.id; s.close()

    sent = {}
    import app.services.training_service as ts
    def fake_send(job_id):
        sent["job"] = job_id
        return "celery-123"
    monkeypatch.setattr(ts, "send_train_task", fake_send)

    from app.main import app
    client = TestClient(app)
    r = client.post("/training-jobs", json={
        "name": "job1", "dataset_version_id": dv_id,
        "base_model": "bert-base-chinese", "task_type": "classification",
        "hyperparams": {"epochs": 1}})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["celery_task_id"] == "celery-123"
    assert sent["job"] == body["id"]
