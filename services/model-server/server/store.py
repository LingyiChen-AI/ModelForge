from server.model_loader import download_model
from server.predictors import build_predictor


class ModelStore:
    def __init__(self):
        self._models = {}  # model_version_id -> (task_type, predictor)

    def load(self, model_version_id, mlflow_model_name, mlflow_version, task_type):
        model_dir = download_model(mlflow_model_name, mlflow_version)
        self._models[model_version_id] = (task_type, build_predictor(task_type, model_dir))

    def get(self, model_version_id):
        return self._models.get(model_version_id)

    def unload(self, model_version_id):
        return self._models.pop(model_version_id, None) is not None

    def loaded_ids(self):
        return list(self._models.keys())


store = ModelStore()
