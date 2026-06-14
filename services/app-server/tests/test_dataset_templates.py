import io, json
import pandas as pd, boto3
from moto import mock_aws
from fastapi.testclient import TestClient
from modelforge_common.enums import TaskType
from app.services.dataset_service import (
    serialize_template, normalize_list_columns, template_dataframe,
)


def test_serialize_template_all_formats():
    for tt in TaskType:
        for fmt in ("csv", "jsonl", "xlsx"):
            content, media, ext = serialize_template(tt, fmt)
            assert content and isinstance(content, bytes)
            assert ext == fmt


def test_jsonl_template_keeps_lists_for_ner():
    content, _, _ = serialize_template(TaskType.NER, "jsonl")
    rows = [json.loads(line) for line in content.decode().splitlines()]
    assert isinstance(rows[0]["tokens"], list) and isinstance(rows[0]["tags"], list)


def test_csv_template_roundtrips_back_to_lists():
    # CSV encodes list columns as JSON strings; normalize parses them back.
    content, _, _ = serialize_template(TaskType.NER, "csv")
    df = pd.read_csv(io.BytesIO(content))
    assert isinstance(df.loc[0, "tokens"], str)  # stored as JSON string in CSV
    df = normalize_list_columns(df, TaskType.NER)
    assert isinstance(df.loc[0, "tokens"], list)
    assert df.loc[0, "tags"][0].startswith("B-")


def test_embedding_optional_neg_blank_becomes_none():
    df = pd.DataFrame({"query": ["q"], "pos": ['["p"]'], "neg": [""]})
    df = normalize_list_columns(df, TaskType.EMBEDDING)
    assert df.loc[0, "pos"] == ["p"]
    assert df.loc[0, "neg"] is None


def _setup(tmp_path):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="datasets")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(eng)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    from tests.conftest import make_user, auth_headers
    d = dbmod.SessionLocal()
    admin = make_user(d, codes=("*",), data_scope="all", email="root@x.com")
    h = auth_headers(admin.id); d.close()
    from app.main import app
    return TestClient(app), h


@mock_aws
def test_template_endpoint_three_formats(tmp_path):
    client, h = _setup(tmp_path)
    ds_id = client.post("/datasets", json={"name": "ner1", "kind": "train",
                        "task_type": "ner"}, headers=h).json()["id"]
    for fmt in ("csv", "jsonl", "xlsx"):
        r = client.get(f"/datasets/{ds_id}/template", params={"fmt": fmt}, headers=h)
        assert r.status_code == 200, (fmt, r.text)
        assert f"template.{fmt}" in r.headers["content-disposition"]
        assert len(r.content) > 0
    bad = client.get(f"/datasets/{ds_id}/template", params={"fmt": "txt"}, headers=h)
    assert bad.status_code == 400


@mock_aws
def test_template_by_type_endpoint(tmp_path):
    client, h = _setup(tmp_path)
    for tt in ("classification", "ner", "pair", "embedding"):
        for fmt in ("csv", "jsonl", "xlsx"):
            r = client.get("/datasets/template", params={"task_type": tt, "fmt": fmt}, headers=h)
            assert r.status_code == 200, (tt, fmt, r.text)
            assert f"{tt}-template.{fmt}" in r.headers["content-disposition"]
    assert client.get("/datasets/template", params={"task_type": "nope", "fmt": "csv"}, headers=h).status_code == 400


@mock_aws
def test_xlsx_upload_ner_stores_lists(tmp_path):
    client, h = _setup(tmp_path)
    ds_id = client.post("/datasets", json={"name": "ner2", "kind": "train",
                        "task_type": "ner"}, headers=h).json()["id"]
    # Build an xlsx the way the template does: list columns as JSON strings.
    df = pd.DataFrame({
        "tokens": [json.dumps(["小", "明"], ensure_ascii=False)],
        "tags": [json.dumps(["B-PER", "I-PER"], ensure_ascii=False)],
    })
    buf = io.BytesIO(); df.to_excel(buf, index=False); buf.seek(0)
    r = client.post(f"/datasets/{ds_id}/versions",
                    files={"file": ("d.xlsx", buf,
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                    headers=h)
    assert r.status_code == 201, r.text
    uri = r.json()["storage_uri"]
    from app.storage import build_storage
    back = build_storage().read_snapshot(uri)
    assert isinstance(back.loc[0, "tokens"], (list, tuple)) or list(back.loc[0, "tokens"])
    assert list(back.loc[0, "tags"]) == ["B-PER", "I-PER"]
