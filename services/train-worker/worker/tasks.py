import json, tempfile
import mlflow
from mlflow.tracking import MlflowClient
import requests
from worker.config import settings
from worker.celery_app import celery_app
from modelforge_common.task_names import TRAIN_TASK, EVAL_TASK
from modelforge_common.enums import JobStatus
from worker.db import (build_engine, set_job_status, set_job_progress, load_job,
                       set_eval_status, set_eval_progress, load_eval_run)
from worker.storage import read_snapshot
from worker.recipes import get_recipe
from worker.mlflow_utils import _configure_mlflow_s3_env
from worker.model_loader import download_model
from worker.evaluators import get_evaluator


def run_recipe(task_type, df, base_model, hyperparams, output_dir, on_progress=None, eval_df=None):
    return get_recipe(task_type).train(df=df, base_model=base_model,
                                       hyperparams=hyperparams, output_dir=output_dir,
                                       on_progress=on_progress, eval_df=eval_df)


def _progress_reporter(engine, job_id):
    """Callback for recipes: update DB progress + log live metrics to MLflow."""
    def cb(frac, metrics, step):
        try:
            set_job_progress(engine, job_id, frac)
        except Exception:
            pass
        try:
            nums = {k: float(v) for k, v in (metrics or {}).items() if isinstance(v, (int, float))}
            if nums:
                mlflow.log_metrics(nums, step=int(step))
        except Exception:
            pass
    return cb


def _register_run_model(run_id: str, model_name: str) -> str:
    """Register a run's `model` artifacts as a new model version (MLflow 3.x).

    Uses the low-level create_model_version with an explicit runs:/ source so the
    registered artifacts stay at the root (predictors load HF files directly).
    """
    client = MlflowClient()
    try:
        client.create_registered_model(model_name)
    except Exception:
        pass  # already exists
    mv = client.create_model_version(name=model_name, source=f"runs:/{run_id}/model", run_id=run_id)
    return mv.version


def report_result(training_job_id: int, run_id: str, model_name: str,
                  version: str, metrics: dict) -> None:
    requests.post(
        f"{settings.app_server_url}/training-jobs/internal/{training_job_id}/result",
        json={"run_id": run_id, "model_name": model_name, "version": version,
              "metrics": {k: float(v) for k, v in metrics.items()
                          if isinstance(v, (int, float))}},
        headers={"X-Internal-Token": settings.internal_token}, timeout=10)


@celery_app.task(name=TRAIN_TASK, bind=True)
def train_task(self, training_job_id: int):
    engine = build_engine()
    set_job_status(engine, training_job_id, JobStatus.RUNNING)
    set_job_progress(engine, training_job_id, 0.0)
    try:
        job = load_job(engine, training_job_id)
        hp = job["hyperparams"]
        hp = json.loads(hp) if isinstance(hp, str) else (hp or {})
        import pandas as pd
        # multiple selected versions are merged (concatenated) into one training frame
        train_uris = job.get("storage_uris") or [job["storage_uri"]]
        df = pd.concat([read_snapshot(u) for u in train_uris], ignore_index=True)
        eval_uris = job.get("eval_storage_uris") or ([job["eval_storage_uri"]] if job.get("eval_storage_uri") else [])
        eval_df = pd.concat([read_snapshot(u) for u in eval_uris], ignore_index=True) if eval_uris else None
        _configure_mlflow_s3_env()
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        # register under the bound model container's name so versions accumulate
        model_name = job.get("model_name") or job["name"]
        with tempfile.TemporaryDirectory() as out:
            # Run created BEFORE training so step metrics stream live and the UI
            # can deep-link to the MLflow run while it is still running.
            with mlflow.start_run(run_name=job["name"]) as run:
                run_id = run.info.run_id
                set_job_status(engine, training_job_id, JobStatus.RUNNING, mlflow_run_id=run_id)
                mlflow.log_params({"base_model": job["base_model"],
                                   **{k: v for k, v in hp.items() if not isinstance(v, (dict, list))}})
                result = run_recipe(job["task_type"], df, job["base_model"], hp, out,
                                    on_progress=_progress_reporter(engine, training_job_id),
                                    eval_df=eval_df)
                mlflow.log_metrics({k: float(v) for k, v in result.metrics.items()
                                    if isinstance(v, (int, float))})
                mlflow.log_artifacts(result.artifact_dir, artifact_path="model")
                version = _register_run_model(run_id, model_name)
        set_job_progress(engine, training_job_id, 1.0)
        set_job_status(engine, training_job_id, JobStatus.SUCCEEDED, mlflow_run_id=run_id)
        try:
            report_result(training_job_id, run_id, model_name, str(version), result.metrics)
        except Exception:
            pass  # callback is best-effort; job already succeeded and is recorded in DB
        return {"run_id": run_id, "model_name": model_name, "version": str(version),
                "metrics": result.metrics}
    except Exception as e:
        set_job_status(engine, training_job_id, JobStatus.FAILED, error=str(e))
        raise


def run_evaluator(task_type, model_dir, df, on_progress=None):
    return get_evaluator(task_type).evaluate(model_dir=model_dir, df=df, on_progress=on_progress)


@celery_app.task(name=EVAL_TASK, bind=True)
def eval_task(self, eval_run_id: int):
    engine = build_engine()
    set_eval_status(engine, eval_run_id, JobStatus.RUNNING)
    set_eval_progress(engine, eval_run_id, 0.05)
    try:
        run = load_eval_run(engine, eval_run_id)
        model_dir = download_model(run["mlflow_model_name"], run["mlflow_version"])
        set_eval_progress(engine, eval_run_id, 0.4)   # model downloaded
        df = read_snapshot(run["storage_uri"])
        set_eval_progress(engine, eval_run_id, 0.5)   # data loaded
        # inference progress maps the evaluator's 0~1 into the 0.5~0.98 band
        def on_progress(frac):
            try:
                set_eval_progress(engine, eval_run_id, 0.5 + 0.48 * max(0.0, min(1.0, frac)))
            except Exception:
                pass
        metrics = run_evaluator(run["task_type"], model_dir, df, on_progress=on_progress)
        set_eval_progress(engine, eval_run_id, 1.0)
        set_eval_status(engine, eval_run_id, JobStatus.SUCCEEDED, results=metrics)
        return {"eval_run_id": eval_run_id, "metrics": metrics}
    except Exception as e:
        set_eval_status(engine, eval_run_id, JobStatus.FAILED, error=str(e))
        raise
