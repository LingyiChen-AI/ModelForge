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
