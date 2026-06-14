from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.training import TrainingJob, Model
from app.models.dataset import DatasetVersion
from app.celery_client import send_train_task   # imported as module-level name for monkeypatch

def _all_exist(db: Session, ids: list[int]) -> bool:
    if not ids:
        return True
    found = db.execute(select(DatasetVersion.id).where(DatasetVersion.id.in_(ids))).scalars().all()
    return set(found) == set(ids)

def create_and_dispatch(db: Session, body, created_by=None) -> TrainingJob:
    model = db.get(Model, body.model_id)
    if not model:
        raise ValueError("model not found, create one first")
    train_ids = body.train_ids
    if not train_ids:
        raise ValueError("dataset_version_ids required")
    if not _all_exist(db, train_ids):
        raise ValueError("dataset_version not found")
    eval_ids = body.eval_ids
    if not _all_exist(db, eval_ids):
        raise ValueError("eval_dataset_version not found")
    job = TrainingJob(name=body.name, model_id=model.id,
                      dataset_version_id=train_ids[0],            # primary (back-compat / worker join)
                      dataset_version_ids=train_ids,
                      eval_dataset_version_id=(eval_ids[0] if eval_ids else None),
                      eval_dataset_version_ids=eval_ids,
                      base_model=body.base_model, task_type=model.task_type,
                      hyperparams=body.hyperparams, created_by=created_by)
    db.add(job); db.commit(); db.refresh(job)
    job.celery_task_id = send_train_task(job.id)
    db.commit(); db.refresh(job)
    return job
