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
