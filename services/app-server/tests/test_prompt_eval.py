from tests.conftest import make_user, auth_headers


def test_prompt_eval_models(session_factory):
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem, PromptEvalOutput
    db = session_factory()
    run = PromptEvalRun(name="r1", eval_type="multi_prompt",
                        prompt_version_ids=[1, 2], model_ids=[3], dataset_version_ids=[4])
    run.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=1, model_id=3, label="A"))
    run.arms.append(PromptEvalArm(arm_index=1, prompt_version_id=2, model_id=3, label="B"))
    db.add(run); db.commit(); db.refresh(run)
    assert run.id and [a.label for a in run.arms] == ["A", "B"]
    it = PromptEvalItem(run_id=run.id, item_index=0, dataset_version_id=4, row_index=0,
                        inputs={"city": "BJ"})
    it.outputs.append(PromptEvalOutput(arm_id=run.arms[0].id, output_text="hi", status="done"))
    db.add(it); db.commit(); db.refresh(it)
    assert it.outputs[0].output_text == "hi" and it.outputs[0].status == "done"


def test_bootstrap_has_prompteval_perms(session_factory):
    from app import bootstrap
    from app.models.rbac import Permission, Role
    from sqlalchemy import select
    db = session_factory()
    bootstrap.seed(db)
    codes = {p.code for p in db.execute(select(Permission)).scalars()}
    assert {"prompteval:read", "prompteval:run"} <= codes
    member = db.execute(select(Role).where(Role.name == "member")).scalar_one()
    viewer = db.execute(select(Role).where(Role.name == "viewer")).scalar_one()
    assert "prompteval:run" in {p.code for p in member.permissions}
    assert "prompteval:read" in {p.code for p in viewer.permissions}
    assert "prompteval:run" not in {p.code for p in viewer.permissions}


def test_prompt_eval_schema(session_factory):
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm
    from app.schemas.prompt_eval import PromptEvalDetailOut
    db = session_factory()
    run = PromptEvalRun(name="r", eval_type="multi_prompt",
                        prompt_version_ids=[1, 2], model_ids=[3], dataset_version_ids=[4])
    run.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=1, model_id=3, label="A"))
    db.add(run); db.commit(); db.refresh(run)
    out = PromptEvalDetailOut.model_validate(run).model_dump()
    assert out["eval_type"] == "multi_prompt" and out["arms"][0]["label"] == "A"
    assert out["prompt_version_ids"] == [1, 2]


def _seed_prompt_and_dataset(db):
    """建一个有 2 个版本的 prompt(参数 name)、一个 llm 模型、一个 prompt 测试集版本(列含 name)。"""
    from app.models.prompt import Prompt, PromptVersion
    from app.models.llm import LlmProvider, LlmModel
    from app.models.dataset import Dataset, DatasetVersion
    p = Prompt(name="问候")
    p.versions.append(PromptVersion(version_no=1, system_prompt="", user_prompt="你好 {{ name }}", params=["name"]))
    p.versions.append(PromptVersion(version_no=2, system_prompt="", user_prompt="hi {{ name }}", params=["name"]))
    db.add(p)
    prov = LlmProvider(name="prov", base_url="u", api_key="k")
    prov.models.append(LlmModel(model_id="gpt-x"))
    db.add(prov)
    ds = Dataset(name="集", kind="prompt", task_type="prompt")
    db.add(ds); db.commit()
    dv = DatasetVersion(dataset_id=ds.id, version_no=1, storage_uri="s3://x/y",
                        row_count=2, checksum="c", note="", stats={"columns": ["name"]})
    db.add(dv); db.commit(); db.refresh(p); db.refresh(prov); db.refresh(dv)
    return p, prov.models[0], dv


def test_service_validation_and_arms(session_factory, monkeypatch):
    import app.services.prompt_eval_service as svc
    monkeypatch.setattr(svc, "send_prompt_eval_task", lambda rid: "celery-1")
    db = session_factory()
    p, model, dv = _seed_prompt_and_dataset(db)
    v1, v2 = p.versions[0].id, p.versions[1].id

    class Body:
        eval_type = "multi_prompt"; name = "r"
        prompt_version_ids = [v1, v2]; model_ids = [model.id]; dataset_version_ids = [dv.id]
    run = svc.create_and_dispatch(db, Body(), created_by=None)
    assert run.eval_type == "multi_prompt" and len(run.arms) == 2 and run.celery_task_id == "celery-1"

    # single_prompt 记录上一版本
    class Body2:
        eval_type = "single_prompt"; name = "r2"
        prompt_version_ids = [v2]; model_ids = [model.id]; dataset_version_ids = [dv.id]
    run2 = svc.create_and_dispatch(db, Body2(), created_by=None)
    assert len(run2.arms) == 1 and run2.compare_to_version_id == v1

    # 数量约束:multi_prompt 只给 1 个 prompt -> ValueError
    import pytest
    class BadCount:
        eval_type = "multi_prompt"; name = "r"
        prompt_version_ids = [v1]; model_ids = [model.id]; dataset_version_ids = [dv.id]
    with pytest.raises(ValueError):
        svc.create_and_dispatch(db, BadCount(), created_by=None)


def test_service_missing_param(session_factory, monkeypatch):
    import app.services.prompt_eval_service as svc
    monkeypatch.setattr(svc, "send_prompt_eval_task", lambda rid: "c")
    from app.models.prompt import Prompt, PromptVersion
    from app.models.llm import LlmProvider, LlmModel
    from app.models.dataset import Dataset, DatasetVersion
    db = session_factory()
    p = Prompt(name="x"); p.versions.append(PromptVersion(version_no=1, system_prompt="",
              user_prompt="{{ city }}", params=["city"]))
    db.add(p)
    prov = LlmProvider(name="pr", base_url="u", api_key="k"); prov.models.append(LlmModel(model_id="m")); db.add(prov)
    ds = Dataset(name="d", kind="prompt", task_type="prompt"); db.add(ds); db.commit()
    dv = DatasetVersion(dataset_id=ds.id, version_no=1, storage_uri="s", row_count=1,
                        checksum="c", note="", stats={"columns": ["name"]})  # 缺 city
    db.add(dv); db.commit(); db.refresh(p); db.refresh(prov); db.refresh(dv)

    class Body:
        eval_type = "single_prompt"; name = "r"
        prompt_version_ids = [p.versions[0].id]; model_ids = [prov.models[0].id]; dataset_version_ids = [dv.id]
    import pytest
    with pytest.raises(ValueError) as ei:
        svc.create_and_dispatch(db, Body(), created_by=None)
    assert "city" in str(ei.value)


from fastapi.testclient import TestClient


def _client(session_factory, codes):
    db = session_factory()
    u = make_user(db, codes=codes, data_scope="all", email="pe@x.com"); db.close()
    from app.main import app
    return TestClient(app), auth_headers(u.id)


def test_prompt_eval_api(session_factory, monkeypatch):
    import app.services.prompt_eval_service as svc
    monkeypatch.setattr(svc, "send_prompt_eval_task", lambda rid: "celery-1")
    db = session_factory()
    p, model, dv = _seed_prompt_and_dataset(db)
    v1, v2, mid, dvid = p.versions[0].id, p.versions[1].id, model.id, dv.id
    u = make_user(db, codes=("prompteval:read", "prompteval:run"), data_scope="all", email="pe2@x.com")
    H = auth_headers(u.id); db.close()
    from app.main import app
    c = TestClient(app)
    # options
    opts = c.get("/prompt-evals/options", headers=H).json()
    assert any(o["id"] == v1 for o in opts["prompt_versions"])
    assert any(o["id"] == mid for o in opts["models"])
    assert any(o["version_id"] == dvid for o in opts["prompt_datasets"])
    # create
    r = c.post("/prompt-evals", json={"eval_type": "multi_prompt", "name": "r",
               "prompt_version_ids": [v1, v2], "model_ids": [mid], "dataset_version_ids": [dvid]}, headers=H)
    assert r.status_code == 201
    rid = r.json()["id"]
    assert len(r.json()["arms"]) == 2
    # missing param / bad count -> 422
    assert c.post("/prompt-evals", json={"eval_type": "multi_prompt", "name": "r",
               "prompt_version_ids": [v1], "model_ids": [mid], "dataset_version_ids": [dvid]}, headers=H).status_code == 422
    # list + detail
    assert c.get("/prompt-evals", headers=H).json()[0]["id"] == rid
    assert c.get(f"/prompt-evals/{rid}", headers=H).json()["eval_type"] == "multi_prompt"
    assert c.get(f"/prompt-evals/{rid}/items", headers=H).status_code == 200  # 空 items
    assert c.get("/prompt-evals/99999", headers=H).status_code == 404


def test_prompt_eval_api_requires_perm(session_factory):
    c, H = _client(session_factory, ("dataset:read",))
    assert c.get("/prompt-evals", headers=H).status_code == 403
    assert c.post("/prompt-evals", json={"eval_type": "single_prompt", "name": "r",
               "prompt_version_ids": [1], "model_ids": [1], "dataset_version_ids": [1]}, headers=H).status_code == 403
