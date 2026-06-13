import os
import mlflow
from server.config import settings
def _configure_s3_env():
    os.environ["AWS_ACCESS_KEY_ID"] = settings.s3_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = settings.s3_secret_key
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = settings.s3_endpoint_url
def download_model(mlflow_model_name: str, mlflow_version: str) -> str:
    _configure_s3_env()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    return mlflow.artifacts.download_artifacts(
        artifact_uri=f"models:/{mlflow_model_name}/{mlflow_version}")
