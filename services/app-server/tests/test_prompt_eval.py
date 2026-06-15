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
