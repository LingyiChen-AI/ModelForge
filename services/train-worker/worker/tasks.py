import json, tempfile
import requests
from worker.config import settings
from worker.celery_app import celery_app
from modelforge_common.task_names import TRAIN_TASK
from modelforge_common.enums import JobStatus
from worker.db import build_engine, set_job_status, load_job
from worker.storage import read_snapshot
from worker.recipes import get_recipe
from worker.mlflow_utils import log_and_register


def run_recipe(task_type, df, base_model, hyperparams, output_dir):
    return get_recipe(task_type).train(df=df, base_model=base_model,
                                       hyperparams=hyperparams, output_dir=output_dir)


def report_result(training_job_id: int, run_id: str, model_name: str,
                  version: str, metrics: dict) -> None:
    requests.post(
        f"{settings.app_server_url}/training-jobs/internal/{training_job_id}/result",
        json={"run_id": run_id, "model_name": model_name, "version": version,
              "metrics": {k: float(v) for k, v in metrics.items()
                          if isinstance(v, (int, float))}}, timeout=10)


@celery_app.task(name=TRAIN_TASK, bind=True)
def train_task(self, training_job_id: int):
    engine = build_engine()
    set_job_status(engine, training_job_id, JobStatus.RUNNING)
    try:
        job = load_job(engine, training_job_id)
        hp = job["hyperparams"]
        hp = json.loads(hp) if isinstance(hp, str) else (hp or {})
        df = read_snapshot(job["storage_uri"])
        with tempfile.TemporaryDirectory() as out:
            result = run_recipe(job["task_type"], df, job["base_model"], hp, out)
            run_id, model_name, version = log_and_register(
                job_name=job["name"], base_model=job["base_model"], hyperparams=hp,
                metrics=result.metrics, artifact_dir=result.artifact_dir)
        set_job_status(engine, training_job_id, JobStatus.SUCCEEDED, mlflow_run_id=run_id)
        try:
            report_result(training_job_id, run_id, model_name, version, result.metrics)
        except Exception:
            pass  # callback is best-effort; job already succeeded and is recorded in DB
        return {"run_id": run_id, "model_name": model_name, "version": version,
                "metrics": result.metrics}
    except Exception as e:
        set_job_status(engine, training_job_id, JobStatus.FAILED, error=str(e))
        raise
