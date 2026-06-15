from tests.conftest import make_user, auth_headers


def test_provider_model_and_mask(session_factory):
    from app.models.llm import LlmProvider, LlmModel, mask_key
    assert mask_key("sk-1234567890cdef") == "sk-…cdef"
    assert mask_key("abc") == "…"
    assert mask_key("") == ""
    assert mask_key(None) == ""
    db = session_factory()
    p = LlmProvider(name="openai", base_url="https://api.openai.com/v1", api_key="sk-secret-abcd")
    p.models.append(LlmModel(model_id="gpt-4o-mini"))
    db.add(p); db.commit(); db.refresh(p)
    assert p.id and p.enabled is True
    assert p.masked_key == "sk-…abcd"
    assert [m.model_id for m in p.models] == ["gpt-4o-mini"]


def test_provider_delete_cascades_models(session_factory):
    from app.models.llm import LlmProvider, LlmModel
    from sqlalchemy import select
    db = session_factory()
    p = LlmProvider(name="x", base_url="u", api_key="k")
    p.models.append(LlmModel(model_id="m1"))
    db.add(p); db.commit()
    db.delete(p); db.commit()
    assert db.execute(select(LlmModel)).first() is None


def test_bootstrap_has_llm_manage(session_factory):
    from app import bootstrap
    from app.models.rbac import Permission, Role
    from sqlalchemy import select
    db = session_factory()
    bootstrap.seed(db)
    assert db.execute(select(Permission).where(Permission.code == "llm:manage")).scalar_one_or_none()
    admin = db.execute(select(Role).where(Role.name == "admin")).scalar_one()
    assert "llm:manage" in [p.code for p in admin.permissions]


def test_provider_out_masks_key(session_factory):
    from app.models.llm import LlmProvider
    from app.schemas.llm import ProviderOut
    db = session_factory()
    p = LlmProvider(name="x", base_url="u", api_key="sk-supersecret-9999")
    db.add(p); db.commit(); db.refresh(p)
    dumped = ProviderOut.model_validate(p).model_dump()
    assert dumped["masked_key"] == "sk-…9999"
    assert "api_key" not in dumped            # 完整 key 不出 schema


def test_service_crud_and_models(session_factory):
    from app.services import llm_provider_service as svc
    db = session_factory()
    p = svc.create_provider(db, name="x", base_url="u", api_key="sk-aaaa1111",
                            model_ids=["m1", "m1", "m2"], created_by=None)  # 去重
    assert sorted(m.model_id for m in p.models) == ["m1", "m2"]
    # update: api_key 留空不改,改 name/enabled
    svc.update_provider(db, p.id, name="y", enabled=False, api_key=None)
    db.refresh(p)
    assert p.name == "y" and p.enabled is False and p.api_key == "sk-aaaa1111"
    # update: 给了新 key 则替换
    svc.update_provider(db, p.id, api_key="sk-bbbb2222")
    db.refresh(p); assert p.api_key == "sk-bbbb2222"
    # add model + 重复抛 ValueError
    m = svc.add_model(db, p.id, "m3"); assert m.model_id == "m3"
    import pytest
    with pytest.raises(ValueError):
        svc.add_model(db, p.id, "m3")
    # remove model
    assert svc.remove_model(db, m.id) is True
    # delete provider
    assert svc.delete_provider(db, p.id) is True
    assert svc.delete_provider(db, p.id) is False


def test_service_test_model(session_factory, monkeypatch):
    from app.services import llm_provider_service as svc
    from modelforge_common.llm_client import ChatResult, LLMError
    db = session_factory()
    p = svc.create_provider(db, name="x", base_url="u", api_key="k",
                            model_ids=["m1"], created_by=None)
    mid = p.models[0].id
    # 成功路
    monkeypatch.setattr(svc, "llm_chat",
                        lambda *a, **k: ChatResult(content="2", usage=None, raw={}))
    ok = svc.test_model(db, mid)
    assert ok["ok"] is True and ok["reply"] == "2" and ok["error"] is None
    # 失败路
    def boom(*a, **k):
        raise LLMError(401, "unauthorized")
    monkeypatch.setattr(svc, "llm_chat", boom)
    bad = svc.test_model(db, mid)
    assert bad["ok"] is False and bad["reply"] is None and bad["error"] == "unauthorized"
    # 不存在的 model
    assert svc.test_model(db, 99999) is None


from fastapi.testclient import TestClient


def _client_with(session_factory, codes):
    from app import db as dbmod  # noqa: F401
    db = session_factory()
    u = make_user(db, codes=codes, data_scope="all", email="llm@x.com"); db.close()
    from app.main import app
    return TestClient(app), auth_headers(u.id)


def test_llm_api_crud_and_mask(session_factory, monkeypatch):
    import app.services.llm_provider_service as svc
    from modelforge_common.llm_client import ChatResult
    c, H = _client_with(session_factory, ("llm:manage",))
    # create
    r = c.post("/llm/providers", json={"name": "openai", "base_url": "https://api.x/v1",
               "api_key": "sk-secret-7777", "model_ids": ["gpt-4o-mini"]}, headers=H)
    assert r.status_code == 201
    body = r.json()
    pid = body["id"]
    assert body["masked_key"] == "sk-…7777" and "api_key" not in body
    assert body["models"][0]["model_id"] == "gpt-4o-mini"
    mid = body["models"][0]["id"]
    # list
    listed = c.get("/llm/providers", headers=H).json()
    assert listed and listed[0]["masked_key"] == "sk-…7777"
    # patch: 留空不改 key,改 enabled
    c.patch(f"/llm/providers/{pid}", json={"enabled": False, "api_key": ""}, headers=H)
    assert c.get("/llm/providers", headers=H).json()[0]["enabled"] is False
    # add model + 重复 422
    assert c.post(f"/llm/providers/{pid}/models", json={"model_id": "gpt-4o"}, headers=H).status_code == 201
    assert c.post(f"/llm/providers/{pid}/models", json={"model_id": "gpt-4o"}, headers=H).status_code == 422
    # test endpoint(mock client)
    monkeypatch.setattr(svc, "llm_chat", lambda *a, **k: ChatResult(content="2", usage=None, raw={}))
    tr = c.post(f"/llm/models/{mid}/test", headers=H).json()
    assert tr["ok"] is True and tr["reply"] == "2"
    # delete model + provider
    assert c.delete(f"/llm/models/{mid}", headers=H).status_code == 200
    assert c.delete(f"/llm/providers/{pid}", headers=H).status_code == 200
    assert c.delete(f"/llm/providers/{pid}", headers=H).status_code == 404


def test_llm_api_requires_perm(session_factory):
    c, H = _client_with(session_factory, ("dataset:read",))
    assert c.get("/llm/providers", headers=H).status_code == 403
