import requests
from app.config import settings

def load_on_server(model_version) -> None:
    requests.post(f"{settings.model_server_url}/load", json={
        "model_version_id": model_version.id,
        "mlflow_model_name": model_version.mlflow_model_name,
        "mlflow_version": model_version.mlflow_version,
        "task_type": model_version.task_type}, timeout=30).raise_for_status()

def unload_on_server(model_version_id: int) -> None:
    requests.delete(f"{settings.model_server_url}/loaded/{model_version_id}", timeout=10)
