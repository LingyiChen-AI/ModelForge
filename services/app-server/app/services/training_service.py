from sqlalchemy.orm import Session
from app.models.training import TrainingJob
from app.models.dataset import DatasetVersion
from app.celery_client import send_train_task   # imported as module-level name for monkeypatch

def create_and_dispatch(db: Session, body, created_by=None) -> TrainingJob:
    dv = db.get(DatasetVersion, body.dataset_version_id)
    if not dv:
        raise ValueError("dataset_version not found")
    job = TrainingJob(name=body.name, dataset_version_id=body.dataset_version_id,
                      base_model=body.base_model, task_type=body.task_type.value,
                      hyperparams=body.hyperparams, created_by=created_by)
    db.add(job); db.commit(); db.refresh(job)
    job.celery_task_id = send_train_task(job.id)
    db.commit(); db.refresh(job)
    return job
