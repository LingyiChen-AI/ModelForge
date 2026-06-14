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
    from app.models.training import Model
    s = dbmod.SessionLocal()
    ds = Dataset(name="d", kind="train", task_type="classification"); s.add(ds); s.commit()
    dv = DatasetVersion(dataset_id=ds.id, version_no=1, storage_uri="s3://x/y",
                        row_count=2, checksum="c", note=""); s.add(dv); s.commit()
    mdl = Model(name="my-model", task_type="classification"); s.add(mdl); s.commit()
    dv_id = dv.id; model_id = mdl.id; s.close()

    from tests.conftest import make_user, auth_headers
    _d = dbmod.SessionLocal(); _root = make_user(_d, codes=("*",), data_scope="all", email="root_train@x.com")
    H = auth_headers(_root.id); _d.close()

    sent = {}
    import app.services.training_service as ts
    def fake_send(job_id):
        sent["job"] = job_id
        return "celery-123"
    monkeypatch.setattr(ts, "send_train_task", fake_send)

    from app.main import app
    client = TestClient(app)
    r = client.post("/training-jobs", json={
        "name": "job1", "model_id": model_id, "dataset_version_id": dv_id,
        "base_model": "bert-base-chinese", "hyperparams": {"epochs": 1}}, headers=H)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["model_id"] == model_id and body["model_name"] == "my-model"
    assert body["celery_task_id"] == "celery-123"
    assert sent["job"] == body["id"]


def test_create_training_job_multi_dataset(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    eng = create_engine(f"sqlite:///{tmp_path}/t.db"); Base.metadata.create_all(eng)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    from app.models.dataset import Dataset, DatasetVersion
    from app.models.training import Model, TrainingJob
    s = dbmod.SessionLocal()
    train = Dataset(name="分类-训练集", kind="train", task_type="classification"); s.add(train); s.commit()
    v1 = DatasetVersion(dataset_id=train.id, version_no=1, storage_uri="s3://x/v1", row_count=2, checksum="a", note="")
    v2 = DatasetVersion(dataset_id=train.id, version_no=2, storage_uri="s3://x/v2", row_count=3, checksum="b", note="")
    ev = Dataset(name="分类-评估集", kind="eval", task_type="classification"); s.add_all([v1, v2, ev]); s.commit()
    ev1 = DatasetVersion(dataset_id=ev.id, version_no=1, storage_uri="s3://x/e1", row_count=1, checksum="c", note=""); s.add(ev1); s.commit()
    mdl = Model(name="m2", task_type="classification"); s.add(mdl); s.commit()
    ids = dict(v1=v1.id, v2=v2.id, ev1=ev1.id, model=mdl.id); s.close()

    from tests.conftest import make_user, auth_headers
    _d = dbmod.SessionLocal(); _root = make_user(_d, codes=("*",), data_scope="all", email="root_multi@x.com")
    H = auth_headers(_root.id); _d.close()

    import app.services.training_service as ts
    monkeypatch.setattr(ts, "send_train_task", lambda job_id: "celery-xyz")

    from app.main import app
    client = TestClient(app)
    r = client.post("/training-jobs", json={
        "name": "jobm", "model_id": ids["model"],
        "dataset_version_ids": [ids["v1"], ids["v2"]],
        "eval_dataset_version_ids": [ids["ev1"]],
        "base_model": "bert-base-chinese"}, headers=H)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["train_datasets"] == ["分类-训练集 V1", "分类-训练集 V2"]
    assert body["eval_datasets"] == ["分类-评估集 V1"]

    # both versions persisted in the merged list; primary = first
    _d = dbmod.SessionLocal()
    job = _d.get(TrainingJob, body["id"])
    assert job.dataset_version_ids == [ids["v1"], ids["v2"]]
    assert job.dataset_version_id == ids["v1"]
    _d.close()

    # unknown version id is rejected
    r2 = client.post("/training-jobs", json={
        "name": "bad", "model_id": ids["model"],
        "dataset_version_ids": [ids["v1"], 99999],
        "base_model": "bert-base-chinese"}, headers=H)
    assert r2.status_code == 422
