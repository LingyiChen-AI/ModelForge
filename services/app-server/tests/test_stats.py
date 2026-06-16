"""统计页 Prompt 聚合(子项目 E):/stats 计数 + /stats/charts 类型分布,按权限门控。"""
from datetime import datetime
from fastapi.testclient import TestClient
from tests.conftest import make_user, auth_headers


def _seed_eval_data(db):
    """1 prompt+2 版本、1 模型、3 个评测(全状态/类型),含人工+AI verdict 的 item。"""
    from app.models.prompt import Prompt, PromptVersion
    from app.models.llm import LlmProvider, LlmModel
    from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem
    p = Prompt(name="问候")
    p.versions.append(PromptVersion(version_no=1, system_prompt="", user_prompt="hi {{name}}", params=["name"]))
    p.versions.append(PromptVersion(version_no=2, system_prompt="", user_prompt="你好 {{name}}", params=["name"]))
    db.add(p)
    prov = LlmProvider(name="prov", base_url="http://x", api_key="k", enabled=True)
    prov.models.append(LlmModel(model_id="m1"))
    db.add(prov); db.commit()
    pv1 = p.versions[0]; mdl = prov.models[0]

    def run(name, etype, status):
        r = PromptEvalRun(name=name, eval_type=etype, status=status,
                          prompt_version_ids=[pv1.id], model_ids=[mdl.id], dataset_version_ids=[1])
        r.arms.append(PromptEvalArm(arm_index=0, prompt_version_id=pv1.id, model_id=mdl.id, label="A"))
        db.add(r); db.commit(); db.refresh(r)
        return r

    r1 = run("a", "multi_prompt", "succeeded")
    run("b", "multi_model", "running")
    run("c", "single_prompt", "pending")
    # item with both human + AI verdict, and one pending item
    db.add(PromptEvalItem(run_id=r1.id, item_index=0, dataset_version_id=1, row_index=0, inputs={},
                          evaluated_at=datetime(2026, 6, 16), ai_evaluated_at=datetime(2026, 6, 16)))
    db.add(PromptEvalItem(run_id=r1.id, item_index=1, dataset_version_id=1, row_index=1, inputs={}))
    db.commit()


def _client(session_factory, codes, seed=True):
    db = session_factory()
    if seed:
        _seed_eval_data(db)
    u = make_user(db, codes=codes, data_scope="all", email="st@x.com"); db.close()
    from app.main import app
    return TestClient(app), auth_headers(u.id)


def test_stats_includes_prompt_counts(session_factory):
    c, H = _client(session_factory, ("prompt:read", "prompteval:read"))
    d = c.get("/stats", headers=H).json()
    assert d["prompts"] == 1
    assert d["prompt_eval_runs"] == 3
    assert d["prompt_eval_items"] == 2
    assert d["prompt_human_evaluated"] == 1
    assert d["prompt_ai_evaluated"] == 1


def test_charts_includes_prompt_eval_type_breakdown(session_factory):
    c, H = _client(session_factory, ("prompteval:read",))
    d = c.get("/stats/charts", headers=H).json()
    assert d["prompt_eval_runs_by_type"] == {"multi_prompt": 1, "multi_model": 1, "single_prompt": 1}


def test_prompt_stats_gated_by_permission(session_factory):
    # 无 prompt:read / prompteval:read → 不含对应字段(优雅降级,不 403)
    c, H = _client(session_factory, ("dataset:read",))
    d = c.get("/stats", headers=H).json()
    for k in ("prompts", "prompt_eval_runs", "prompt_eval_items",
              "prompt_human_evaluated", "prompt_ai_evaluated"):
        assert k not in d
    assert "prompt_eval_runs_by_type" not in c.get("/stats/charts", headers=H).json()
