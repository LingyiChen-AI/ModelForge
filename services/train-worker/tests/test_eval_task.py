from sqlalchemy import create_engine, text
import pandas as pd, worker.tasks as tasks


def test_eval_task_orchestration(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE eval_runs (id INTEGER PRIMARY KEY, model_version_id INTEGER, "
                       "dataset_version_id INTEGER, status TEXT, progress REAL DEFAULT 0, "
                       "results TEXT, error TEXT, metric_config TEXT)"))
        c.execute(text("CREATE TABLE model_versions (id INTEGER PRIMARY KEY, mlflow_model_name TEXT, "
                       "mlflow_version TEXT, task_type TEXT)"))
        c.execute(text("CREATE TABLE dataset_versions (id INTEGER PRIMARY KEY, storage_uri TEXT)"))
        c.execute(text("INSERT INTO model_versions VALUES (7,'ModelForge-j','2','classification')"))
        c.execute(text("INSERT INTO dataset_versions VALUES (3,'s3://b/k')"))
        c.execute(text("INSERT INTO eval_runs (id,model_version_id,dataset_version_id,status,metric_config) "
                       "VALUES (1,7,3,'pending','{}')"))
    monkeypatch.setattr(tasks, "build_engine", lambda: eng)
    monkeypatch.setattr(tasks, "download_model", lambda name, version: str(tmp_path))
    monkeypatch.setattr(tasks, "read_snapshot",
                        lambda uri: pd.DataFrame({"text": ["a"], "label": ["x"]}))
    monkeypatch.setattr(tasks, "run_evaluator",
                        lambda *a, **k: {"accuracy": 0.75, "f1": 0.7})

    tasks.eval_task.run(eval_run_id=1)

    with eng.connect() as c:
        row = c.execute(text("SELECT status, results FROM eval_runs WHERE id=1")).one()
    assert row.status == "succeeded" and '"accuracy": 0.75' in row.results
