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


class FixedVersionStat(BaseModel):
    version_label: str   # the model-version label that fixed these badcases (e.g. "5")
    count: int           # how many badcases this version fixed


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
    fixed_versions: list[FixedVersionStat] = []   # per-version fix counts (V5 修复 12 条, V6 修复 8 条)
