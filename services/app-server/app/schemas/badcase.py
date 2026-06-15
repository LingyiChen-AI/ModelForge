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
    annotated_by_name: str | None = None
    annotated_at: datetime | None = None
    dataset_version_id: int | None
    created_at: datetime
    fixed_by: list[dict] = []

    class Config:
        from_attributes = True


class BadcaseSummaryOut(BaseModel):
    model_version_id: int
    model_name: str | None = None
    model_version_label: str | None = None
    task_type: str
    reported: int    # total badcases for this model version
    annotated: int   # status in (annotated, used)
    used: int        # status == used (already turned into a dataset)
    pending: int     # status == reported (awaiting annotation)
    fixed: int       # fixed_by non-empty
    fixed_versions: list[str] = []   # distinct model-version labels that fixed any badcase (V4, V7)
