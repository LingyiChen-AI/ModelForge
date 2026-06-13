import mlflow
from worker.mlflow_utils import _configure_mlflow_s3_env
from worker.config import settings


def download_model(mlflow_model_name: str, mlflow_version: str) -> str:
    """Download a registered model's artifacts to a local dir, return its path."""
    _configure_mlflow_s3_env()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    return mlflow.artifacts.download_artifacts(
        artifact_uri=f"models:/{mlflow_model_name}/{mlflow_version}")
