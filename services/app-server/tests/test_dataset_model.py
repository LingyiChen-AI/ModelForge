from app.models.base import Base
import app.models  # noqa


def test_dataset_tables_registered():
    assert "datasets" in Base.metadata.tables
    assert "dataset_versions" in Base.metadata.tables
    cols = Base.metadata.tables["dataset_versions"].columns.keys()
    assert {"id", "dataset_id", "version_no", "storage_uri",
            "row_count", "checksum", "stats", "note"} <= set(cols)
