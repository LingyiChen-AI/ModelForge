import json
from sqlalchemy import create_engine, text
from worker.db import set_job_status, set_eval_status, JobStatus


def test_set_eval_status_persists_predictions(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE eval_runs (id INTEGER PRIMARY KEY, status TEXT, "
                       "results TEXT, predictions TEXT, error TEXT)"))
        c.execute(text("INSERT INTO eval_runs (id, status) VALUES (1, 'pending')"))
    preds = [{"row": 0, "input": "好评", "expected": "pos", "predicted": "pos", "correct": True}]
    set_eval_status(eng, 1, JobStatus.SUCCEEDED, results={"accuracy": 1.0}, predictions=preds)
    with eng.connect() as c:
        row = c.execute(text("SELECT status, results, predictions FROM eval_runs WHERE id=1")).one()
    assert row.status == "succeeded"
    assert json.loads(row.results) == {"accuracy": 1.0}
    assert json.loads(row.predictions) == preds


def test_set_job_status(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE training_jobs (id INTEGER PRIMARY KEY, "
                       "status TEXT, mlflow_run_id TEXT, error TEXT)"))
        c.execute(text("INSERT INTO training_jobs (id, status) VALUES (1, 'pending')"))
    set_job_status(eng, 1, JobStatus.RUNNING)
    with eng.connect() as c:
        assert c.execute(text("SELECT status FROM training_jobs WHERE id=1")).scalar() == "running"
    set_job_status(eng, 1, JobStatus.FAILED, error="boom")
    with eng.connect() as c:
        row = c.execute(text("SELECT status, error FROM training_jobs WHERE id=1")).one()
        assert row.status == "failed" and row.error == "boom"
