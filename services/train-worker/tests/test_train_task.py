import contextlib
from types import SimpleNamespace
from sqlalchemy import create_engine, text
import pandas as pd, worker.tasks as tasks
from worker.recipes.base import TrainResult

def test_train_task_orchestration(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE training_jobs (id INTEGER PRIMARY KEY, name TEXT, "
                       "model_id INTEGER, base_model TEXT, task_type TEXT, hyperparams TEXT, "
                       "status TEXT, progress REAL DEFAULT 0, dataset_version_id INTEGER, "
                       "eval_dataset_version_id INTEGER, dataset_version_ids TEXT, "
                       "eval_dataset_version_ids TEXT, mlflow_run_id TEXT, error TEXT)"))
        c.execute(text("CREATE TABLE models (id INTEGER PRIMARY KEY, name TEXT)"))
        c.execute(text("CREATE TABLE dataset_versions (id INTEGER PRIMARY KEY, storage_uri TEXT)"))
        c.execute(text("INSERT INTO dataset_versions (id, storage_uri) VALUES (1,'s3://b/k1'),(2,'s3://b/k2')"))
        # two train versions selected -> worker merges (concatenates) both snapshots
        c.execute(text("INSERT INTO training_jobs (id,name,base_model,task_type,hyperparams,"
                       "status,dataset_version_id,dataset_version_ids) "
                       "VALUES (1,'j','m','classification','{}','pending',1,'[1,2]')"))

    monkeypatch.setattr(tasks, "build_engine", lambda: eng)
    monkeypatch.setattr(tasks, "read_snapshot",
                        lambda uri: pd.DataFrame({"text": ["a"], "label": ["x"]}))
    seen_rows = {}
    fake = TrainResult(metrics={"accuracy": 1.0}, artifact_dir=str(tmp_path), label_names=["x"])
    def fake_run(task_type, df, *a, **k):
        seen_rows["n"] = len(df)
        return fake
    monkeypatch.setattr(tasks, "run_recipe", fake_run)
    monkeypatch.setattr(tasks, "report_result", lambda *a, **k: None)
    monkeypatch.setattr(tasks, "_configure_mlflow_s3_env", lambda: None)
    monkeypatch.setattr(tasks, "_register_run_model", lambda run_id, name: "3")

    captured = {}

    @contextlib.contextmanager
    def _start_run(run_name=None):
        yield SimpleNamespace(info=SimpleNamespace(run_id="run-1"))

    fake_mlflow = SimpleNamespace(
        set_tracking_uri=lambda uri: None,
        start_run=_start_run,
        log_params=lambda p: None,
        log_metrics=lambda m, step=None: captured.update(m),
        log_artifacts=lambda d, artifact_path=None: None,
        register_model=lambda uri, name: SimpleNamespace(version="3"),
    )
    monkeypatch.setattr(tasks, "mlflow", fake_mlflow)

    tasks.train_task.run(training_job_id=1)

    with eng.connect() as c:
        row = c.execute(text("SELECT status, mlflow_run_id, progress FROM training_jobs WHERE id=1")).one()
    assert row.status == "succeeded" and row.mlflow_run_id == "run-1"
    assert row.progress == 1.0
    assert captured == {"accuracy": 1.0}
    assert seen_rows["n"] == 2   # both selected versions merged into one frame
