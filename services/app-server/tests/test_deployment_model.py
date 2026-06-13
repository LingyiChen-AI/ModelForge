from app.models.base import Base
import app.models  # noqa


def test_deployments_table():
    assert "deployments" in Base.metadata.tables
    cols = Base.metadata.tables["deployments"].columns.keys()
    assert {"id", "model_version_id", "endpoint", "mode", "status", "replicas", "config", "error"} <= set(cols)
