from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.config import settings
from app.models.training import Model, TrainingJob, ModelVersion, EvalRun, Deployment
from app.modelserver_client import unload_on_server


def _mlflow_client():
    import mlflow
    from mlflow.tracking import MlflowClient
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    return MlflowClient()


def _delete_versions(db: Session, mv_ids: list[int], del_mlflow: bool) -> None:
    """Delete model versions + their dependents (deployments, eval runs); optionally MLflow."""
    if not mv_ids:
        return
    versions = db.execute(select(ModelVersion).where(ModelVersion.id.in_(mv_ids))).scalars().all()
    for dep in db.execute(select(Deployment).where(Deployment.model_version_id.in_(mv_ids))).scalars().all():
        try:
            unload_on_server(dep.model_version_id)
        except Exception:
            pass
        db.delete(dep)
    db.execute(delete(EvalRun).where(EvalRun.model_version_id.in_(mv_ids)))
    if del_mlflow:
        client = _mlflow_client()
        for mv in versions:
            try:
                client.delete_model_version(mv.mlflow_model_name, mv.mlflow_version)
            except Exception:
                pass
    for mv in versions:
        db.delete(mv)


def delete_deployment(db: Session, dep_id: int) -> None:
    dep = db.get(Deployment, dep_id)
    if not dep:
        raise ValueError("deployment not found")
    try:
        unload_on_server(dep.model_version_id)
    except Exception:
        pass
    db.delete(dep); db.commit()


def delete_eval_run(db: Session, run_id: int) -> None:
    run = db.get(EvalRun, run_id)
    if not run:
        raise ValueError("eval run not found")
    db.delete(run); db.commit()


def delete_training_job(db: Session, job_id: int, cascade: bool) -> None:
    job = db.get(TrainingJob, job_id)
    if not job:
        raise ValueError("training job not found")
    mv_ids = list(db.execute(select(ModelVersion.id).where(
        ModelVersion.source_training_job_id == job_id)).scalars())
    _delete_versions(db, mv_ids, cascade)
    if cascade and job.mlflow_run_id:
        try:
            _mlflow_client().delete_run(job.mlflow_run_id)
        except Exception:
            pass
    db.delete(job); db.commit()


def delete_model(db: Session, model_id: int, cascade: bool) -> None:
    m = db.get(Model, model_id)
    if not m:
        raise ValueError("model not found")
    mv_ids = list(db.execute(select(ModelVersion.id).where(ModelVersion.model_id == model_id)).scalars())
    _delete_versions(db, mv_ids, cascade)
    db.execute(delete(TrainingJob).where(TrainingJob.model_id == model_id))
    if cascade:
        try:
            _mlflow_client().delete_registered_model(m.name)
        except Exception:
            pass
    db.delete(m); db.commit()
