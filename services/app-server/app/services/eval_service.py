from sqlalchemy.orm import Session
from app.models.training import EvalRun, ModelVersion
from app.models.dataset import DatasetVersion
from app.celery_client import send_eval_task   # module-level name (monkeypatchable)

def create_and_dispatch(db: Session, body, created_by=None) -> EvalRun:
    if not db.get(ModelVersion, body.model_version_id):
        raise ValueError("model_version not found")
    if not db.get(DatasetVersion, body.dataset_version_id):
        raise ValueError("dataset_version not found")
    run = EvalRun(model_version_id=body.model_version_id,
                  dataset_version_id=body.dataset_version_id,
                  metric_config=body.metric_config, created_by=created_by)
    db.add(run); db.commit(); db.refresh(run)
    run.celery_task_id = send_eval_task(run.id)
    db.commit(); db.refresh(run)
    return run
