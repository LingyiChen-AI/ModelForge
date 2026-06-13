from pydantic import BaseModel

class EvalRunCreate(BaseModel):
    model_version_id: int
    dataset_version_id: int
    metric_config: dict = {}

class EvalRunOut(BaseModel):
    id: int
    model_version_id: int
    dataset_version_id: int
    status: str
    celery_task_id: str | None
    results: dict
    error: str | None
    class Config: from_attributes = True
