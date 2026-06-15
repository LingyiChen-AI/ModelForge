from tests.conftest import make_user, auth_headers


def test_prompt_models_and_latest(session_factory):
    from app.models.prompt import Prompt, PromptVersion
    db = session_factory()
    p = Prompt(name="问候")
    p.versions.append(PromptVersion(version_no=1, system_prompt="你是助手",
                                    user_prompt="你好 {{ name }}", params=["name"]))
    p.versions.append(PromptVersion(version_no=2, system_prompt="",
                                    user_prompt="{{ a }}{{ b }}", params=["a", "b"]))
    db.add(p); db.commit(); db.refresh(p)
    assert p.id and p.latest_version_no == 2 and p.latest_params == ["a", "b"]


def test_prompt_delete_cascades_versions(session_factory):
    from app.models.prompt import Prompt, PromptVersion
    from sqlalchemy import select
    db = session_factory()
    p = Prompt(name="x"); p.versions.append(PromptVersion(version_no=1))
    db.add(p); db.commit()
    db.delete(p); db.commit()
    assert db.execute(select(PromptVersion)).first() is None


def test_bootstrap_has_prompt_perms(session_factory):
    from app import bootstrap
    from app.models.rbac import Permission, Role
    from sqlalchemy import select
    db = session_factory()
    bootstrap.seed(db)
    codes = {p.code for p in db.execute(select(Permission)).scalars()}
    assert {"prompt:read", "prompt:write"} <= codes
    admin = db.execute(select(Role).where(Role.name == "admin")).scalar_one()
    member = db.execute(select(Role).where(Role.name == "member")).scalar_one()
    viewer = db.execute(select(Role).where(Role.name == "viewer")).scalar_one()
    assert "prompt:write" in {p.code for p in admin.permissions}
    assert "prompt:write" in {p.code for p in member.permissions}
    assert "prompt:read" in {p.code for p in viewer.permissions}
    assert "prompt:write" not in {p.code for p in viewer.permissions}


class _FakeStore:
    def write_snapshot(self, dataset_id, version_no, df):
        return (f"mem://{dataset_id}/{version_no}", "checksum", len(df))


def test_validate_prompt_rows_rejects_empty():
    import pandas as pd, pytest
    from app.services.dataset_service import validate_prompt_rows
    with pytest.raises(ValueError):
        validate_prompt_rows(pd.DataFrame())                 # 0 列
    with pytest.raises(ValueError):
        validate_prompt_rows(pd.DataFrame(columns=["a"]))    # 0 行


def test_create_prompt_version_skips_task_validation(session_factory):
    import pandas as pd
    from app.models.dataset import Dataset
    from app.services.dataset_service import create_version
    db = session_factory()
    ds = Dataset(name="pset", kind="prompt", task_type="prompt"); db.add(ds); db.commit()
    df = pd.DataFrame([{"city": "BJ", "name": "x"}])
    v = create_version(db, _FakeStore(), ds, df, created_by=None)
    assert v.stats["columns"] == ["city", "name"] and v.version_no == 1


def test_prompt_out_serializes_latest(session_factory):
    from app.models.prompt import Prompt, PromptVersion
    from app.schemas.prompt import PromptOut, PromptDetailOut
    db = session_factory()
    p = Prompt(name="x")
    p.versions.append(PromptVersion(version_no=1, system_prompt="s", user_prompt="{{ a }}", params=["a"]))
    db.add(p); db.commit(); db.refresh(p)
    out = PromptOut.model_validate(p).model_dump()
    assert out["latest_version_no"] == 1 and out["latest_params"] == ["a"]
    detail = PromptDetailOut.model_validate(p).model_dump()
    assert detail["versions"][0]["user_prompt"] == "{{ a }}"


def test_prompt_service_create_and_version(session_factory):
    from app.services import prompt_service as svc
    db = session_factory()
    p = svc.create_prompt(db, name="问候", system_prompt="你是 {{ role }}",
                          user_prompt="你好 {{ name }}", note="", created_by=None)
    assert p.versions[0].version_no == 1
    assert p.versions[0].params == ["role", "name"]   # system ∪ user, 保序
    v2 = svc.add_version(db, p.id, system_prompt="", user_prompt="{{ name }}{{ name }}",
                         note="", created_by=None)
    assert v2.version_no == 2 and v2.params == ["name"]
    # 不存在的 prompt
    assert svc.add_version(db, 99999, system_prompt="", user_prompt="", note="", created_by=None) is None
    # 语法错误 -> ValueError
    import pytest
    with pytest.raises(ValueError):
        svc.create_prompt(db, name="bad", system_prompt="{{ }}", user_prompt="",
                          note="", created_by=None)


def test_prompt_service_validate():
    from app.services import prompt_service as svc
    ok = svc.validate("{{ a }}", "{{ b }}")
    assert ok["params"] == ["a", "b"] and ok["errors"] == []
    bad = svc.validate("{{ a-b }}", "")
    assert bad["errors"] != []


import io
import boto3
import pandas as pd
from moto import mock_aws
from fastapi.testclient import TestClient


def _client(session_factory, codes):
    db = session_factory()
    u = make_user(db, codes=codes, data_scope="all", email="pr@x.com"); db.close()
    from app.main import app
    return TestClient(app), auth_headers(u.id)


def test_prompt_api_flow(session_factory):
    c, H = _client(session_factory, ("prompt:read", "prompt:write"))
    # validate
    v = c.post("/prompts/validate", json={"system_prompt": "{{ a }}", "user_prompt": "{{ b }}"}, headers=H).json()
    assert v["params"] == ["a", "b"] and v["errors"] == []
    # create
    r = c.post("/prompts", json={"name": "问候", "system_prompt": "你是 {{ role }}",
               "user_prompt": "你好 {{ name }}"}, headers=H)
    assert r.status_code == 201
    body = r.json(); pid = body["id"]
    assert body["latest_version_no"] == 1 and body["versions"][0]["params"] == ["role", "name"]
    # invalid syntax -> 422
    assert c.post("/prompts", json={"name": "bad", "system_prompt": "{{ }}", "user_prompt": ""}, headers=H).status_code == 422
    # add version
    av = c.post(f"/prompts/{pid}/versions", json={"system_prompt": "", "user_prompt": "{{ x }}"}, headers=H)
    assert av.status_code == 201 and av.json()["version_no"] == 2
    # list + get + versions
    assert c.get("/prompts", headers=H).json()[0]["id"] == pid
    assert c.get(f"/prompts/{pid}", headers=H).json()["latest_version_no"] == 2
    assert len(c.get(f"/prompts/{pid}/versions", headers=H).json()) == 2
    # 404
    assert c.get("/prompts/99999", headers=H).status_code == 404


def test_prompt_api_requires_perm(session_factory):
    c, H = _client(session_factory, ("dataset:read",))
    assert c.get("/prompts", headers=H).status_code == 403


@mock_aws
def test_prompt_dataset_endpoint(tmp_path):
    # 上传走真实存储路径,按既有 dataset 上传测试的套路:@mock_aws + 建桶 + 手动建 engine
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="datasets")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Base
    eng = create_engine(f"sqlite:///{tmp_path}/t.db"); Base.metadata.create_all(eng)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    d = dbmod.SessionLocal()
    u = make_user(d, codes=("dataset:read", "dataset:write"), data_scope="all", email="pds@x.com")
    H = auth_headers(u.id); d.close()
    from app.main import app
    c = TestClient(app)
    r = c.post("/datasets/prompt", json={"name": "城市集"}, headers=H)
    assert r.status_code == 201
    ds = r.json()
    assert ds["kind"] == "prompt" and ds["task_type"] == "prompt"
    # 上传一版:列即参数,存进 stats.columns(create_version 已对所有 kind 写 stats.columns)
    df = pd.DataFrame({"city": ["BJ", "SH"], "name": ["xiaoming", "lily"]})
    buf = io.BytesIO(); df.to_csv(buf, index=False); buf.seek(0)
    up = c.post(f"/datasets/{ds['id']}/versions",
                files={"file": ("p.csv", buf, "text/csv")}, headers=H)
    assert up.status_code == 201 and up.json()["row_count"] == 2
