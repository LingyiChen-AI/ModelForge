import io, pandas as pd, boto3
from moto import mock_aws
from fastapi.testclient import TestClient
from tests.conftest import make_user, auth_headers

@mock_aws
def test_own_scope_isolation(session_factory):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="datasets")
    S = session_factory; db = S()
    a = make_user(db, codes=("dataset:read","dataset:write"), data_scope="own", email="a@x.com")
    b = make_user(db, codes=("dataset:read","dataset:write"), data_scope="own", email="b@x.com")
    aid, bid = a.id, b.id; db.close()

    from app.main import app
    c = TestClient(app)
    r = c.post("/datasets", json={"name":"da","kind":"train","task_type":"classification"},
               headers=auth_headers(aid))
    assert r.status_code == 201
    ds_a = r.json()["id"]
    assert c.get("/datasets", headers=auth_headers(bid)).json() == []
    assert len(c.get("/datasets", headers=auth_headers(aid)).json()) == 1
    assert c.get(f"/datasets/{ds_a}/versions", headers=auth_headers(bid)).status_code == 404

@mock_aws
def test_requires_permission(session_factory):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="datasets")
    S = session_factory; db = S()
    viewer = make_user(db, codes=("dataset:read",), data_scope="own", email="v@x.com")
    vid = viewer.id; db.close()
    from app.main import app
    c = TestClient(app)
    assert c.post("/datasets", json={"name":"x","kind":"train","task_type":"classification"},
                  headers=auth_headers(vid)).status_code == 403
    assert c.get("/datasets").status_code == 401
