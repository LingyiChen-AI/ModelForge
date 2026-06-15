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


def test_ai_eval_service_prompt_and_dispatch(session_factory, monkeypatch):
    import app.services.ai_eval_service as svc
    from app.ai_eval_defaults import DEFAULT_AI_EVAL_PROMPT
    db = session_factory()
    assert svc.get_prompt(db) == DEFAULT_AI_EVAL_PROMPT
    svc.set_prompt(db, "我的评判指令")
    assert svc.get_prompt(db) == "我的评判指令"
    svc.set_prompt(db, "v2")
    assert svc.get_prompt(db) == "v2"

    from app.models.llm import LlmProvider, LlmModel
    from app.models.prompt_eval import PromptEvalRun
    prov = LlmProvider(name="p", base_url="u", api_key="k"); prov.models.append(LlmModel(model_id="m"))
    db.add(prov)
    run = PromptEvalRun(name="r", eval_type="multi_prompt", prompt_version_ids=[1],
                        model_ids=[1], dataset_version_ids=[1]); db.add(run); db.commit()
    db.refresh(prov); db.refresh(run)
    sent = {}
    monkeypatch.setattr(svc, "send_prompt_ai_eval_task",
                        lambda rid, mid, jp: sent.update(rid=rid, mid=mid, jp=jp) or "celery-ai-1")
    svc.dispatch(db, run.id, prov.models[0].id)
    assert sent["rid"] == run.id and sent["mid"] == prov.models[0].id and sent["jp"] == "v2"
    import pytest
    with pytest.raises(ValueError):
        svc.dispatch(db, run.id, 999999)
