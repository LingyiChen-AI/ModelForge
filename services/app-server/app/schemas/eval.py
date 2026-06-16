from datetime import datetime
from pydantic import BaseModel

class EvalRunCreate(BaseModel):
    model_version_id: int
    dataset_version_id: int
    metric_config: dict = {}

class EvalRunOut(BaseModel):
    id: int
    model_version_id: int
    model_name: str | None = None
    model_version_label: str | None = None
    dataset_version_id: int
    dataset_name: str | None = None
    dataset_version_no: int | None = None
    status: str
    progress: float
    celery_task_id: str | None
    results: dict
    error: str | None
    has_predictions: bool = False
    created_at: datetime
    created_by_name: str | None = None
    class Config: from_attributes = True
