from fastapi.testclient import TestClient

def test_annotate_and_build_dataset(session_factory, monkeypatch):
    from tests.test_badcase_api import _setup_version
    mvid = _setup_version(session_factory)
    from app import db as dbmod
    from app.models.badcase import Badcase
    import sqlalchemy
    db = dbmod.SessionLocal()
    for t in ["怎么退货", "在哪开发票"]:
        db.add(Badcase(model_version_id=mvid, task_type="classification",
                       input={"text": t}, inference={"label": "物流查询"}, status="reported"))
    db.commit()
    ids = [b.id for b in db.execute(sqlalchemy.select(Badcase)).scalars()]
    db.close()

    from tests.conftest import make_user, auth_headers
    d = dbmod.SessionLocal(); u = make_user(d, codes=("*",), data_scope="all", email="bc@x.com"); d.close()
    H = auth_headers(u.id)

    # stub storage so no real MinIO is needed
    import app.services.badcase_service as bs
    class _Store:
        def write_snapshot(self, dataset_id, version_no, df):
            return (f"s3://x/{dataset_id}/v{version_no}", "sum", len(df))
    monkeypatch.setattr(bs, "build_storage", lambda: _Store())

    from app.main import app
    c = TestClient(app)
    # build before annotate -> 422
    assert c.post("/badcases/build-dataset", json={"badcase_ids": ids}, headers=H).status_code == 422
    # annotate both
    for i in ids:
        assert c.patch(f"/badcases/{i}/annotate", json={"annotation": {"label": "售后服务"}}, headers=H).status_code == 200
    # build -> creates badcase- dataset
    r = c.post("/badcases/build-dataset", json={"badcase_ids": ids}, headers=H)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["dataset_name"].startswith("badcase-") and body["row_count"] == 2
    # cases now used
    assert c.get(f"/badcases/{ids[0]}", headers=H).json()["status"] == "used"
