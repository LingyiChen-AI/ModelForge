from tests.conftest import make_user, auth_headers


def test_ai_columns_and_setting(session_factory):
    from datetime import datetime, timezone
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem
    from app.models.setting import AppSetting
    db = session_factory()
    run = PromptEvalRun(name="r", eval_type="multi_prompt",
                        prompt_version_ids=[1], model_ids=[2], dataset_version_ids=[3])
    run.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=1, model_id=2, label="A"))
    db.add(run); db.commit(); db.refresh(run)
    it = PromptEvalItem(run_id=run.id, item_index=0, dataset_version_id=3, row_index=0, inputs={})
    it.ai_winner_arm_id = run.arms[0].id
    it.ai_model_id = 2
    it.ai_reasoning = "because A is best"
    it.ai_evaluated_at = datetime.now(timezone.utc)
    db.add(it); db.commit(); db.refresh(it)
    assert it.ai_winner_arm_id == run.arms[0].id and it.ai_all_bad is False and it.ai_is_good is None
    assert it.ai_reasoning == "because A is best"
    s = AppSetting(key="ai_eval_prompt", value="judge!"); db.add(s); db.commit()
    assert db.get(AppSetting, "ai_eval_prompt").value == "judge!"
