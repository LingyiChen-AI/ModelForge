from datetime import datetime
from pydantic import BaseModel

class TrainingJobCreate(BaseModel):
    name: str
    model_id: int                                  # bind to a named model container
    dataset_version_ids: list[int] = []            # train set versions (merged)
    eval_dataset_version_ids: list[int] = []       # eval/validation set versions (merged)
    dataset_version_id: int | None = None          # legacy single (back-compat)
    eval_dataset_version_id: int | None = None     # legacy single (back-compat)
    base_model: str
    hyperparams: dict = {}

    @property
    def train_ids(self) -> list[int]:
        ids = list(self.dataset_version_ids)
        if not ids and self.dataset_version_id is not None:
            ids = [self.dataset_version_id]
        # de-dup, preserve order
        seen, out = set(), []
        for i in ids:
            if i not in seen:
                seen.add(i); out.append(i)
        return out

    @property
    def eval_ids(self) -> list[int]:
        ids = list(self.eval_dataset_version_ids)
        if not ids and self.eval_dataset_version_id is not None:
            ids = [self.eval_dataset_version_id]
        seen, out = set(), []
        for i in ids:
            if i not in seen:
                seen.add(i); out.append(i)
        return out

class TrainingJobOut(BaseModel):
    id: int
    name: str
    model_id: int | None
    model_name: str | None = None
    status: str
    progress: float
    celery_task_id: str | None
    mlflow_run_id: str | None
    error: str | None
    created_at: datetime
    created_by_name: str | None = None
    train_datasets: list[str] = []   # ["分类-训练集 V1", "分类-训练集 V2"] (merged)
    eval_datasets: list[str] = []
    metrics: dict = {}               # train metrics of the produced model version (empty until succeeded)
    class Config: from_attributes = True
