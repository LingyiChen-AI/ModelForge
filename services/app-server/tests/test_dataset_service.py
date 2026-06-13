import pandas as pd
import pytest
from app.services.dataset_service import validate_rows, REQUIRED_COLUMNS
from modelforge_common.enums import TaskType


def test_required_columns_classification():
    assert REQUIRED_COLUMNS[TaskType.CLASSIFICATION] == ["text", "label"]


def test_validate_rows_ok():
    df = pd.DataFrame({"text": ["a"], "label": ["x"]})
    validate_rows(df, TaskType.CLASSIFICATION)  # 不抛异常


def test_validate_rows_missing_column():
    df = pd.DataFrame({"text": ["a"]})
    with pytest.raises(ValueError, match="missing columns"):
        validate_rows(df, TaskType.CLASSIFICATION)
