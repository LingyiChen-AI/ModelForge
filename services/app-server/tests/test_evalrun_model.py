from app.models.base import Base
import app.models  # noqa


def test_eval_runs_table():
    assert "eval_runs" in Base.metadata.tables
    cols = Base.metadata.tables["eval_runs"].columns.keys()
    assert {"id", "model_version_id", "dataset_version_id", "metric_config",
            "status", "celery_task_id", "results", "per_sample_uri", "error"} <= set(cols)
