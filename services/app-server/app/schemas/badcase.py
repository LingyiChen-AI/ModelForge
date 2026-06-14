from datetime import datetime
from pydantic import BaseModel


class BadcaseReportIn(BaseModel):
    model_version_id: int
    input: dict
    inference: dict = {}
    source_ref: str | None = None


class BadcaseAnnotateIn(BaseModel):
    annotation: dict


class BuildDatasetIn(BaseModel):
    badcase_ids: list[int]
    name: str | None = None


class BadcaseOut(BaseModel):
    id: int
    model_version_id: int
    model_name: str | None = None
    model_version_label: str | None = None
    task_type: str
    input: dict
    inference: dict
    category: str | None
    source: str | None
    source_ref: str | None
    status: str
    annotation: dict | None
    dataset_version_id: int | None
    created_at: datetime

    class Config:
        from_attributes = True
