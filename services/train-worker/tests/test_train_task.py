from sqlalchemy import create_engine, text
import pandas as pd, worker.tasks as tasks
from worker.recipes.base import TrainResult

def test_train_task_orchestration(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE training_jobs (id INTEGER PRIMARY KEY, name TEXT, "
                       "base_model TEXT, task_type TEXT, hyperparams TEXT, status TEXT, "
                       "dataset_version_id INTEGER, mlflow_run_id TEXT, error TEXT)"))
        c.execute(text("CREATE TABLE dataset_versions (id INTEGER PRIMARY KEY, storage_uri TEXT)"))
        c.execute(text("INSERT INTO dataset_versions (id, storage_uri) VALUES (1,'s3://b/k')"))
        c.execute(text("INSERT INTO training_jobs (id,name,base_model,task_type,hyperparams,"
                       "status,dataset_version_id) VALUES (1,'j','m','classification','{}','pending',1)"))

    monkeypatch.setattr(tasks, "build_engine", lambda: eng)
    monkeypatch.setattr(tasks, "read_snapshot",
                        lambda uri: pd.DataFrame({"text": ["a"], "label": ["x"]}))
    fake = TrainResult(metrics={"accuracy": 1.0}, artifact_dir=str(tmp_path), label_names=["x"])
    monkeypatch.setattr(tasks, "run_recipe", lambda *a, **k: fake)
    captured = {}
    monkeypatch.setattr(tasks, "log_and_register",
                        lambda **k: captured.update(k) or ("run-1", "ModelForge-1", "3"))

    tasks.train_task.run(training_job_id=1)

    with eng.connect() as c:
        row = c.execute(text("SELECT status, mlflow_run_id FROM training_jobs WHERE id=1")).one()
    assert row.status == "succeeded" and row.mlflow_run_id == "run-1"
    assert captured["metrics"] == {"accuracy": 1.0}
