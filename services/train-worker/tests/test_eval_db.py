from sqlalchemy import create_engine, text
from worker.db import set_eval_status, load_eval_run, JobStatus


def test_set_eval_status_and_load(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE eval_runs (id INTEGER PRIMARY KEY, model_version_id INTEGER, "
                       "dataset_version_id INTEGER, status TEXT, results TEXT, error TEXT, metric_config TEXT)"))
        c.execute(text("CREATE TABLE model_versions (id INTEGER PRIMARY KEY, mlflow_model_name TEXT, "
                       "mlflow_version TEXT, task_type TEXT)"))
        c.execute(text("CREATE TABLE dataset_versions (id INTEGER PRIMARY KEY, storage_uri TEXT)"))
        c.execute(text("INSERT INTO model_versions VALUES (7,'ModelForge-j','2','classification')"))
        c.execute(text("INSERT INTO dataset_versions VALUES (3,'s3://b/k')"))
        c.execute(text("INSERT INTO eval_runs (id,model_version_id,dataset_version_id,status,metric_config) "
                       "VALUES (1,7,3,'pending','{}')"))
    set_eval_status(eng, 1, JobStatus.RUNNING)
    info = load_eval_run(eng, 1)
    assert info["mlflow_model_name"] == "ModelForge-j" and info["mlflow_version"] == "2"
    assert info["task_type"] == "classification" and info["storage_uri"] == "s3://b/k"
    set_eval_status(eng, 1, JobStatus.SUCCEEDED, results={"accuracy": 0.8})
    with eng.connect() as c:
        row = c.execute(text("SELECT status, results FROM eval_runs WHERE id=1")).one()
    assert row.status == "succeeded" and '"accuracy"' in row.results
