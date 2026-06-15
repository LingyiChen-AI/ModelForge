from datetime import datetime
from pydantic import BaseModel
from modelforge_common.enums import TaskType, DatasetKind


class DatasetCreate(BaseModel):
    name: str
    kind: DatasetKind
    task_type: TaskType


class DatasetOut(BaseModel):
    id: int
    name: str
    kind: str
    task_type: str
    created_at: datetime
    created_by_name: str | None = None

    class Config:
        from_attributes = True


class DatasetVersionOut(BaseModel):
    id: int
    dataset_id: int
    version_no: int
    storage_uri: str
    row_count: int
    checksum: str
    note: str
    created_at: datetime
    created_by_name: str | None = None

    class Config:
        from_attributes = True


class DatasetVersionLite(BaseModel):
    id: int
    version_no: int
    row_count: int

    class Config:
        from_attributes = True


class DatasetTreeOut(BaseModel):
    """A dataset with its versions, for cascade/version pickers (one-shot, no N+1)."""
    id: int
    name: str
    kind: str
    task_type: str
    versions: list[DatasetVersionLite] = []

    class Config:
        from_attributes = True
