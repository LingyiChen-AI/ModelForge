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
