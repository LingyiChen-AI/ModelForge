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
    # per-user 隔离 + 一键还原
    assert svc.get_prompt(db, 7) == DEFAULT_AI_EVAL_PROMPT and svc.is_custom(db, 7) is False
    svc.set_prompt(db, 7, "我的评判指令")
    assert svc.get_prompt(db, 7) == "我的评判指令" and svc.is_custom(db, 7) is True
    assert svc.get_prompt(db, 8) == DEFAULT_AI_EVAL_PROMPT   # 用户 8 不受用户 7 影响
    svc.reset_prompt(db, 7)
    assert svc.get_prompt(db, 7) == DEFAULT_AI_EVAL_PROMPT and svc.is_custom(db, 7) is False
    svc.set_prompt(db, 7, "v2")

    from app.models.llm import LlmProvider, LlmModel
    from app.models.prompt_eval import PromptEvalRun
    prov = LlmProvider(name="p", base_url="u", api_key="k"); prov.models.append(LlmModel(model_id="m"))
    db.add(prov)
    run = PromptEvalRun(name="r", eval_type="multi_prompt", prompt_version_ids=[1],
                        model_ids=[1], dataset_version_ids=[1]); db.add(run); db.commit()
    db.refresh(prov); db.refresh(run)
    sent = {}
    monkeypatch.setattr(svc, "send_prompt_ai_eval_task",
                        lambda rid, mid, jp, c=20: sent.update(rid=rid, mid=mid, jp=jp, c=c) or "celery-ai-1")
    svc.dispatch(db, run.id, prov.models[0].id, 7)
    assert sent["rid"] == run.id and sent["mid"] == prov.models[0].id and sent["jp"] == "v2"
    import pytest
    with pytest.raises(ValueError):
        svc.dispatch(db, run.id, 999999, 7)


from fastapi.testclient import TestClient


def test_settings_and_trigger_api(session_factory, monkeypatch):
    import app.services.ai_eval_service as svc
    from app.models.llm import LlmProvider, LlmModel
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem
    db = session_factory()
    prov = LlmProvider(name="p", base_url="u", api_key="k"); prov.models.append(LlmModel(model_id="m"))
    db.add(prov)
    run = PromptEvalRun(name="r", eval_type="multi_prompt", prompt_version_ids=[1],
                        model_ids=[1], dataset_version_ids=[1])
    run.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=1, model_id=1, label="A"))
    db.add(run); db.commit(); db.refresh(prov); db.refresh(run)
    it = PromptEvalItem(run_id=run.id, item_index=0, dataset_version_id=1, row_index=0, inputs={})
    db.add(it); db.commit()
    mid, rid, iid = prov.models[0].id, run.id, it.id
    admin = make_user(db, codes=("llm:manage", "prompteval:read", "prompteval:annotate"), data_scope="all", email="ad@x.com")
    H = auth_headers(admin.id); db.close()
    from app.main import app
    monkeypatch.setattr(svc, "send_prompt_ai_eval_task", lambda rid, mid, jp, c=20: "celery-ai-1")
    c = TestClient(app)
    g = c.get("/settings/ai-eval-prompt", headers=H).json()
    assert "JSON" in g["value"] and g["is_custom"] is False
    assert c.put("/settings/ai-eval-prompt", json={"value": "改过了"}, headers=H).status_code == 200
    g2 = c.get("/settings/ai-eval-prompt", headers=H).json()
    assert g2["value"] == "改过了" and g2["is_custom"] is True
    # 一键还原 → 回默认、is_custom=false
    assert c.delete("/settings/ai-eval-prompt", headers=H).status_code == 200
    g3 = c.get("/settings/ai-eval-prompt", headers=H).json()
    assert "JSON" in g3["value"] and g3["is_custom"] is False
    assert c.post(f"/prompt-evals/{rid}/ai-evaluate", json={"model_id": mid}, headers=H).status_code == 200
    assert c.post(f"/prompt-evals/{rid}/ai-evaluate", json={"model_id": 999999}, headers=H).status_code == 422
    items = c.get(f"/prompt-evals/{rid}/items", headers=H).json()
    assert items[0]["ai_winner_arm_id"] is None and "ai_reasoning" in items[0]


def test_settings_requires_perm(session_factory):
    db = session_factory()
    u = make_user(db, codes=("prompteval:read",), data_scope="all", email="np@x.com")
    H = auth_headers(u.id); db.close()
    from app.main import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    assert c.get("/settings/ai-eval-prompt", headers=H).status_code == 403
