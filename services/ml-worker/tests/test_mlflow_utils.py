import os
import worker.mlflow_utils as mu
from worker.config import settings


def test_configure_s3_env_sets_credentials_from_settings(monkeypatch):
    for k in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "MLFLOW_S3_ENDPOINT_URL"]:
        monkeypatch.delenv(k, raising=False)
    mu._configure_mlflow_s3_env()
    assert os.environ["AWS_ACCESS_KEY_ID"] == settings.s3_access_key
    assert os.environ["AWS_SECRET_ACCESS_KEY"] == settings.s3_secret_key
    assert os.environ["MLFLOW_S3_ENDPOINT_URL"] == settings.s3_endpoint_url
