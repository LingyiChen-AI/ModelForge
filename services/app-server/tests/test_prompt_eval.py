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


def test_item_verdict_columns(session_factory):
    from datetime import datetime, timezone
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem
    from app.models.user import User
    from app.models.rbac import Role
    db = session_factory()
    role = Role(name="r-v", data_scope="all"); db.add(role); db.commit()
    u = User(name="judge", email="j@x.com", role_id=role.id); db.add(u); db.commit()
    run = PromptEvalRun(name="r", eval_type="multi_prompt",
                        prompt_version_ids=[1], model_ids=[2], dataset_version_ids=[3])
    run.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=1, model_id=2, label="A"))
    db.add(run); db.commit(); db.refresh(run)
    it = PromptEvalItem(run_id=run.id, item_index=0, dataset_version_id=3, row_index=0, inputs={})
    it.winner_arm_id = run.arms[0].id
    it.evaluated_by = u.id
    it.evaluated_at = datetime.now(timezone.utc)
    db.add(it); db.commit(); db.refresh(it)
    assert it.winner_arm_id == run.arms[0].id and it.all_bad is False and it.is_good is None
    assert it.annotated_by_name == "judge"


def test_bootstrap_has_prompteval_annotate(session_factory):
    from app import bootstrap
    from app.models.rbac import Permission, Role
    from sqlalchemy import select
    db = session_factory()
    bootstrap.seed(db)
    assert db.execute(select(Permission).where(Permission.code == "prompteval:annotate")).scalar_one_or_none()
    member = db.execute(select(Role).where(Role.name == "member")).scalar_one()
    viewer = db.execute(select(Role).where(Role.name == "viewer")).scalar_one()
    assert "prompteval:annotate" in {p.code for p in member.permissions}
    assert "prompteval:annotate" not in {p.code for p in viewer.permissions}


def _seed_eval_run(db, eval_type, n_arms=2):
    """建一个 run + n_arms 个 arm + 一个 item(无 output),返回 (run, [arm...], item)。"""
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem
    run = PromptEvalRun(name="r", eval_type=eval_type,
                        prompt_version_ids=[1], model_ids=[2], dataset_version_ids=[3])
    for i in range(n_arms):
        run.arms.append(PromptEvalArm(arm_index=i, prompt_version_id=1, model_id=2, label=f"L{i}"))
    db.add(run); db.commit(); db.refresh(run)
    it = PromptEvalItem(run_id=run.id, item_index=0, dataset_version_id=3, row_index=0, inputs={})
    db.add(it); db.commit(); db.refresh(it)
    return run, run.arms, it


def test_submit_verdict_multi_and_single(session_factory):
    import app.services.prompt_eval_service as svc
    db = session_factory()
    run, arms, it = _seed_eval_run(db, "multi_prompt", 2)

    class WIN: winner_arm_id = None; all_bad = False; is_good = None
    WIN.winner_arm_id = arms[1].id
    out = svc.submit_verdict(db, it.id, WIN, user_id=None)
    assert out.winner_arm_id == arms[1].id and out.evaluated_at is not None and out.all_bad is False

    class AB: winner_arm_id = None; all_bad = True; is_good = None
    _, _, it2 = _seed_eval_run(db, "multi_prompt", 2)
    out2 = svc.submit_verdict(db, it2.id, AB, user_id=None)
    assert out2.all_bad is True and out2.winner_arm_id is None

    import pytest
    class NONE: winner_arm_id = None; all_bad = False; is_good = None
    _, _, it3 = _seed_eval_run(db, "multi_prompt", 2)
    with pytest.raises(ValueError):
        svc.submit_verdict(db, it3.id, NONE, user_id=None)

    class BADARM: winner_arm_id = 999999; all_bad = False; is_good = None
    _, _, it4 = _seed_eval_run(db, "multi_prompt", 2)
    with pytest.raises(ValueError):
        svc.submit_verdict(db, it4.id, BADARM, user_id=None)

    class GOOD: winner_arm_id = None; all_bad = False; is_good = True
    _, _, its = _seed_eval_run(db, "single_prompt", 1)
    outs = svc.submit_verdict(db, its.id, GOOD, user_id=None)
    assert outs.is_good is True and outs.evaluated_at is not None

    class NOGOOD: winner_arm_id = None; all_bad = False; is_good = None
    _, _, its2 = _seed_eval_run(db, "single_prompt", 1)
    with pytest.raises(ValueError):
        svc.submit_verdict(db, its2.id, NOGOOD, user_id=None)

    assert svc.submit_verdict(db, 999999, GOOD, user_id=None) is None


def test_stats_multi_and_single(session_factory):
    from datetime import datetime, timezone
    from app.models.prompt_eval import PromptEvalItem, PromptEvalArm, PromptEvalRun
    from app.services import prompt_eval_stats as st
    db = session_factory()
    run, arms, it = _seed_eval_run(db, "multi_prompt", 3)
    it.winner_arm_id = arms[0].id; it.evaluated_at = datetime.now(timezone.utc)
    for w in (arms[0].id, arms[1].id):
        x = PromptEvalItem(run_id=run.id, item_index=99, dataset_version_id=3, row_index=0,
                           inputs={}, winner_arm_id=w, evaluated_at=datetime.now(timezone.utc))
        db.add(x)
    db.commit()
    s = st.stats(db, run.id)
    by = {a["arm_id"]: a for a in s["arms"]}
    assert by[arms[0].id]["wins"] == 2 and by[arms[1].id]["wins"] == 1
    assert s["best_arm_id"] == arms[0].id and s["evaluated"] == 3

    from app.models.prompt import Prompt, PromptVersion
    p = Prompt(name="pp")
    p.versions.append(PromptVersion(version_no=1, system_prompt="", user_prompt="{{x}}", params=["x"]))
    p.versions.append(PromptVersion(version_no=2, system_prompt="", user_prompt="{{x}}", params=["x"]))
    db.add(p); db.commit(); db.refresh(p)
    v1, v2 = p.versions[0].id, p.versions[1].id
    prev = PromptEvalRun(name="prev", eval_type="single_prompt", prompt_version_ids=[v1],
                         model_ids=[2], dataset_version_ids=[3])
    prev.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=v1, model_id=2, label="L"))
    db.add(prev); db.commit(); db.refresh(prev)
    db.add(PromptEvalItem(run_id=prev.id, item_index=0, dataset_version_id=3, row_index=0,
                          inputs={}, is_good=False, evaluated_at=datetime.now(timezone.utc)))
    db.commit()
    cur = PromptEvalRun(name="cur", eval_type="single_prompt", prompt_version_ids=[v2],
                        model_ids=[2], dataset_version_ids=[3], compare_to_version_id=v1)
    cur.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=v2, model_id=2, label="L2"))
    db.add(cur); db.commit(); db.refresh(cur)
    db.add(PromptEvalItem(run_id=cur.id, item_index=0, dataset_version_id=3, row_index=0,
                          inputs={}, is_good=True, evaluated_at=datetime.now(timezone.utc)))
    db.commit()
    s2 = st.stats(db, cur.id)
    assert s2["good"] == 1 and s2["bad"] == 0
    assert s2["comparison"]["improved"] == 1 and s2["comparison"]["regressed"] == 0
    assert s2["comparison"]["comparable"] == 1
