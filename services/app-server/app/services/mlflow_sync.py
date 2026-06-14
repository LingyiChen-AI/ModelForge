from sqlalchemy.orm import Session
from app.models.training import TrainingJob, ModelVersion


def upsert_model_version_from_result(db: Session, training_job_id: int,
                                     result: dict) -> ModelVersion:
    job = db.get(TrainingJob, training_job_id)
    if not job:
        raise ValueError("training job not found")
    mv = ModelVersion(
        name=result["model_name"], source_training_job_id=job.id,
        mlflow_model_name=result["model_name"], mlflow_version=str(result["version"]),
        task_type=job.task_type, base_model=job.base_model,
        train_metrics=result.get("metrics", {}),
        created_by=job.created_by,
        artifact_uri=f"models:/{result['model_name']}/{result['version']}")
    db.add(mv); db.commit(); db.refresh(mv)
    return mv
