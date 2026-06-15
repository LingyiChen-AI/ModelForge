import json
import pandas as pd
from sqlalchemy import create_engine, text


def _setup(engine):
    with engine.begin() as c:
        c.execute(text("CREATE TABLE prompt_eval_runs (id INTEGER PRIMARY KEY, eval_type TEXT, "
                       "status TEXT, progress REAL, error TEXT, dataset_version_ids TEXT)"))
        c.execute(text("CREATE TABLE prompt_eval_arms (id INTEGER PRIMARY KEY, run_id INTEGER, "
                       "arm_index INTEGER, prompt_version_id INTEGER, model_id INTEGER, label TEXT)"))
        c.execute(text("CREATE TABLE prompt_eval_items (id INTEGER PRIMARY KEY, run_id INTEGER, "
                       "item_index INTEGER, dataset_version_id INTEGER, row_index INTEGER, inputs TEXT)"))
        c.execute(text("CREATE TABLE prompt_eval_outputs (id INTEGER PRIMARY KEY, item_id INTEGER, "
                       "arm_id INTEGER, output_text TEXT, status TEXT, error TEXT, latency_ms INTEGER)"))
        c.execute(text("CREATE TABLE prompt_versions (id INTEGER PRIMARY KEY, system_prompt TEXT, user_prompt TEXT)"))
        c.execute(text("CREATE TABLE llm_models (id INTEGER PRIMARY KEY, provider_id INTEGER, model_id TEXT)"))
        c.execute(text("CREATE TABLE llm_providers (id INTEGER PRIMARY KEY, base_url TEXT, api_key TEXT)"))
        c.execute(text("CREATE TABLE dataset_versions (id INTEGER PRIMARY KEY, storage_uri TEXT)"))
        c.execute(text("INSERT INTO llm_providers VALUES (1,'http://u','k')"))
        c.execute(text("INSERT INTO llm_models VALUES (10,1,'gpt-x')"))
        c.execute(text("INSERT INTO prompt_versions VALUES (5,'你是助手','你好 {{ name }}')"))
        c.execute(text("INSERT INTO dataset_versions VALUES (3,'s3://b/k')"))
        c.execute(text("INSERT INTO prompt_eval_runs (id,eval_type,status,progress,dataset_version_ids) "
                       "VALUES (1,'multi_prompt','pending',0,'[3]')"))
        c.execute(text("INSERT INTO prompt_eval_arms VALUES (100,1,0,5,10,'A')"))
        c.execute(text("INSERT INTO prompt_eval_arms VALUES (101,1,1,5,10,'B')"))


def test_run_prompt_eval(tmp_path, monkeypatch):
    from modelforge_common.llm_client import ChatResult, LLMError
    import worker.prompt_eval as pe
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    _setup(eng)
    # 2 行测试集
    monkeypatch.setattr(pe, "read_snapshot", lambda uri: pd.DataFrame({"name": ["小明", "小红"]}))
    calls = []
    def fake_chat(base_url, api_key, model_id, messages, **kw):
        calls.append((model_id, messages))
        if "小红" in messages[-1]["content"]:
            raise LLMError(500, "boom")
        return ChatResult(content="OK:" + messages[-1]["content"], usage=None, raw={})
    monkeypatch.setattr(pe, "llm_chat", fake_chat)

    pe.run_prompt_eval(eng, 1)

    with eng.connect() as c:
        items = c.execute(text("SELECT count(*) FROM prompt_eval_items")).scalar()
        outs = c.execute(text("SELECT count(*) FROM prompt_eval_outputs")).scalar()
        done = c.execute(text("SELECT count(*) FROM prompt_eval_outputs WHERE status='done'")).scalar()
        err = c.execute(text("SELECT count(*) FROM prompt_eval_outputs WHERE status='error'")).scalar()
        run = c.execute(text("SELECT status, progress FROM prompt_eval_runs WHERE id=1")).one()
    assert items == 2 and outs == 4          # 2 行 × 2 臂
    assert done == 2 and err == 2            # 小红的两臂失败
    assert run.status == "succeeded" and run.progress == 1.0
    # system 进了 messages
    assert calls[0][1][0]["role"] == "system"
