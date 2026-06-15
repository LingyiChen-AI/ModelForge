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
