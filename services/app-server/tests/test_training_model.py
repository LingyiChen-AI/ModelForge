from app.models.base import Base
import app.models  # noqa


def test_training_tables():
    assert "training_jobs" in Base.metadata.tables
    assert "model_versions" in Base.metadata.tables
    cols = Base.metadata.tables["training_jobs"].columns.keys()
    assert {"dataset_version_id", "base_model", "task_type", "hyperparams",
            "status", "celery_task_id", "mlflow_run_id", "error"} <= set(cols)
