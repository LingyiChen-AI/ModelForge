from pydantic import BaseModel
from modelforge_common.enums import TaskType

class TrainingJobCreate(BaseModel):
    name: str
    dataset_version_id: int
    base_model: str
    task_type: TaskType
    hyperparams: dict = {}

class TrainingJobOut(BaseModel):
    id: int
    name: str
    status: str
    celery_task_id: str | None
    mlflow_run_id: str | None
    error: str | None
    class Config: from_attributes = True
