from sqlalchemy import create_engine, text


def _setup(engine):
    with engine.begin() as c:
        c.execute(text("CREATE TABLE prompt_eval_runs (id INTEGER PRIMARY KEY, eval_type TEXT, "
                       "ai_status TEXT, ai_progress REAL, ai_error TEXT)"))
        c.execute(text("CREATE TABLE prompt_eval_arms (id INTEGER PRIMARY KEY, run_id INTEGER, arm_index INTEGER)"))
        c.execute(text("CREATE TABLE prompt_eval_items (id INTEGER PRIMARY KEY, run_id INTEGER, inputs TEXT, "
                       "ai_winner_arm_id INTEGER, ai_all_bad INTEGER, ai_is_good INTEGER, ai_model_id INTEGER, "
                       "ai_reasoning TEXT, ai_evaluated_at TIMESTAMP)"))
        c.execute(text("CREATE TABLE prompt_eval_outputs (id INTEGER PRIMARY KEY, item_id INTEGER, arm_id INTEGER, output_text TEXT)"))
        c.execute(text("CREATE TABLE llm_models (id INTEGER PRIMARY KEY, provider_id INTEGER, model_id TEXT)"))
        c.execute(text("CREATE TABLE llm_providers (id INTEGER PRIMARY KEY, base_url TEXT, api_key TEXT)"))
        c.execute(text("INSERT INTO llm_providers VALUES (1,'http://u','k')"))
        c.execute(text("INSERT INTO llm_models VALUES (9,1,'judge-x')"))
        c.execute(text("INSERT INTO prompt_eval_runs (id, eval_type) VALUES (1,'multi_prompt')"))
        c.execute(text("INSERT INTO prompt_eval_arms VALUES (10,1,0)"))
        c.execute(text("INSERT INTO prompt_eval_arms VALUES (11,1,1)"))
        c.execute(text("INSERT INTO prompt_eval_items (id,run_id,inputs) VALUES (100,1,'{\"q\":\"x\"}')"))
        c.execute(text("INSERT INTO prompt_eval_outputs VALUES (1000,100,10,'ans A')"))
        c.execute(text("INSERT INTO prompt_eval_outputs VALUES (1001,100,11,'ans B')"))


def test_run_prompt_ai_eval(tmp_path, monkeypatch):
    from modelforge_common.llm_client import ChatResult
    import worker.prompt_ai_eval as pe
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    _setup(eng)
    monkeypatch.setattr(pe, "llm_chat",
                        lambda *a, **k: ChatResult(content='评判结果:{"winner": 2}', usage=None, raw={}))
    pe.run_prompt_ai_eval(eng, run_id=1, model_id=9, judge_prompt="judge")
    with eng.connect() as c:
        row = c.execute(text("SELECT ai_winner_arm_id, ai_model_id, ai_reasoning, ai_evaluated_at "
                             "FROM prompt_eval_items WHERE id=100")).one()
    assert row.ai_winner_arm_id == 11      # winner 2 -> arms[1] (arm_index 1) -> id 11
    assert row.ai_model_id == 9 and row.ai_evaluated_at is not None and "winner" in row.ai_reasoning


def test_ai_eval_bad_json_does_not_abort(tmp_path, monkeypatch):
    from modelforge_common.llm_client import ChatResult
    import worker.prompt_ai_eval as pe
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    _setup(eng)
    monkeypatch.setattr(pe, "llm_chat", lambda *a, **k: ChatResult(content="不是 JSON", usage=None, raw={}))
    pe.run_prompt_ai_eval(eng, run_id=1, model_id=9, judge_prompt="judge")
    with eng.connect() as c:
        row = c.execute(text("SELECT ai_winner_arm_id, ai_reasoning, ai_evaluated_at "
                             "FROM prompt_eval_items WHERE id=100")).one()
    assert row.ai_winner_arm_id is None and row.ai_evaluated_at is not None and row.ai_reasoning == "不是 JSON"


def test_ai_eval_only_pending(tmp_path, monkeypatch):
    from modelforge_common.llm_client import ChatResult
    import worker.prompt_ai_eval as pe
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    _setup(eng)
    with eng.begin() as c:
        c.execute(text("UPDATE prompt_eval_items SET ai_evaluated_at='2020-01-01' WHERE id=100"))
    called = []
    monkeypatch.setattr(pe, "llm_chat", lambda *a, **k: called.append(1) or ChatResult(content="{}", usage=None, raw={}))
    pe.run_prompt_ai_eval(eng, run_id=1, model_id=9, judge_prompt="judge")
    assert called == []
