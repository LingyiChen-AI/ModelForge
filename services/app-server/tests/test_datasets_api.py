import io, pandas as pd, boto3
from moto import mock_aws
from fastapi.testclient import TestClient

@mock_aws
def test_dataset_create_upload_list(monkeypatch, tmp_path):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="datasets")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    test_engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(test_engine)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=test_engine, expire_on_commit=False)

    from tests.conftest import make_user, auth_headers
    _d = dbmod.SessionLocal()
    _admin = make_user(_d, codes=("*",), data_scope="all", email="root@x.com")
    h = auth_headers(_admin.id); _d.close()

    from app.main import app
    client = TestClient(app)

    r = client.post("/datasets", json={"name": "d1", "kind": "train",
                                        "task_type": "classification"}, headers=h)
    assert r.status_code == 201
    ds_id = r.json()["id"]

    df = pd.DataFrame({"text": ["a", "b"], "label": ["x", "y"]})
    buf = io.BytesIO(); df.to_csv(buf, index=False); buf.seek(0)
    r = client.post(f"/datasets/{ds_id}/versions",
                    files={"file": ("d.csv", buf, "text/csv")}, headers=h)
    assert r.status_code == 201
    assert r.json()["version_no"] == 1 and r.json()["row_count"] == 2

    r = client.get(f"/datasets/{ds_id}/versions", headers=h)
    assert len(r.json()) == 1
