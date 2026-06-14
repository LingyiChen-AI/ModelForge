from app.models.base import Base
import app.models  # noqa


def test_created_by_present():
    t = Base.metadata.tables
    for tbl in ("training_jobs", "model_versions", "eval_runs", "deployments"):
        assert "created_by" in t[tbl].columns.keys()
