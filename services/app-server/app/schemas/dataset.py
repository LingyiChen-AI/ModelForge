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
