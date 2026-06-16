import os

import mlflow
from worker.config import settings


def _configure_mlflow_s3_env() -> None:
    """Point MLflow's internal boto3 client at MinIO/S3 using our settings.

    MLflow's artifact store authenticates via the default boto3 credential
    chain, which reads these standard env vars. We populate them from Settings
    so the worker process doesn't need AWS_* exported manually before launch.
    """
    os.environ["AWS_ACCESS_KEY_ID"] = settings.s3_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = settings.s3_secret_key
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = settings.s3_endpoint_url


def log_and_register(*, job_name: str, base_model: str, hyperparams: dict,
                     metrics: dict, artifact_dir: str) -> tuple[str, str, str]:
    _configure_mlflow_s3_env()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    model_name = job_name  # use the job's timestamp name verbatim
    with mlflow.start_run(run_name=job_name) as run:
        mlflow.log_params({"base_model": base_model, **hyperparams})
        mlflow.log_metrics({k: float(v) for k, v in metrics.items()
                            if isinstance(v, (int, float))})
        mlflow.log_artifacts(artifact_dir, artifact_path="model")
        result = mlflow.register_model(
            f"runs:/{run.info.run_id}/model", model_name)
    return run.info.run_id, model_name, result.version
