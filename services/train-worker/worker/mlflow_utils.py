import mlflow
from worker.config import settings


def log_and_register(*, job_name: str, base_model: str, hyperparams: dict,
                     metrics: dict, artifact_dir: str) -> tuple[str, str, str]:
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    model_name = f"ModelForge-{job_name}"
    with mlflow.start_run(run_name=job_name) as run:
        mlflow.log_params({"base_model": base_model, **hyperparams})
        mlflow.log_metrics({k: float(v) for k, v in metrics.items()
                            if isinstance(v, (int, float))})
        mlflow.log_artifacts(artifact_dir, artifact_path="model")
        result = mlflow.register_model(
            f"runs:/{run.info.run_id}/model", model_name)
    return run.info.run_id, model_name, result.version
