import pandas as pd
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from modelforge_common.enums import TaskType
from app.models.dataset import Dataset, DatasetVersion
from app.storage import SnapshotStorage


REQUIRED_COLUMNS = {
    TaskType.CLASSIFICATION: ["text", "label"],
    TaskType.NER: ["tokens", "tags"],
    TaskType.PAIR: ["text_a", "text_b"],
    TaskType.EMBEDDING: ["query", "pos"],
}


def validate_rows(df: pd.DataFrame, task_type: TaskType) -> None:
    required = REQUIRED_COLUMNS[task_type]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns for {task_type.value}: {missing}")
    if len(df) == 0:
        raise ValueError("dataset is empty")


def create_version(db: Session, store: SnapshotStorage, dataset: Dataset,
                   df: pd.DataFrame, note: str = "") -> DatasetVersion:
    validate_rows(df, TaskType(dataset.task_type))
    next_no = (db.execute(
        select(func.coalesce(func.max(DatasetVersion.version_no), 0))
        .where(DatasetVersion.dataset_id == dataset.id)).scalar()) + 1
    uri, checksum, rows = store.write_snapshot(dataset.id, next_no, df)
    version = DatasetVersion(
        dataset_id=dataset.id, version_no=next_no, storage_uri=uri,
        row_count=rows, checksum=checksum, note=note,
        stats={"columns": list(df.columns)})
    db.add(version)
    db.commit()
    db.refresh(version)
    return version
