from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.authz import has_permission, apply_scope
from app.models.user import User
from app.models.dataset import Dataset
from app.models.training import Model, TrainingJob, ModelVersion, EvalRun, Deployment

router = APIRouter(prefix="/stats", tags=["stats"])


def _count(db: Session, user: User, model, *conds) -> int:
    # apply_scope restricts to the user's data scope (own/all); conds add filters
    stmt = apply_scope(select(func.count()).select_from(model), model, user)
    for c in conds:
        stmt = stmt.where(c)
    return db.execute(stmt).scalar() or 0


@router.get("")
def stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Core counts, scoped to the user's permissions and data scope."""
    out: dict[str, int] = {}
    if has_permission(user, "dataset:read"):
        out["datasets"] = _count(db, user, Dataset)
    if has_permission(user, "model:read"):
        out["models"] = _count(db, user, Model)
        out["model_versions"] = _count(db, user, ModelVersion)
    if has_permission(user, "training:read"):
        out["training_jobs"] = _count(db, user, TrainingJob)
        out["running_jobs"] = _count(db, user, TrainingJob, TrainingJob.status == "running")
        out["succeeded_jobs"] = _count(db, user, TrainingJob, TrainingJob.status == "succeeded")
    if has_permission(user, "eval:read"):
        out["eval_runs"] = _count(db, user, EvalRun)
    if has_permission(user, "deploy:read"):
        out["deployments"] = _count(db, user, Deployment)
        out["running_deployments"] = _count(db, user, Deployment, Deployment.status == "running")
    return out


def _group(db: Session, user: User, model, col) -> dict[str, int]:
    stmt = apply_scope(select(col, func.count()).group_by(col), model, user)
    return {str(k): int(v) for k, v in db.execute(stmt).all()}


@router.get("/charts")
def charts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Grouped breakdowns for dashboard reports, scoped like /stats."""
    out: dict[str, dict] = {}
    if has_permission(user, "training:read"):
        out["jobs_by_status"] = _group(db, user, TrainingJob, TrainingJob.status)
    if has_permission(user, "model:read"):
        out["versions_by_task"] = _group(db, user, ModelVersion, ModelVersion.task_type)
    if has_permission(user, "dataset:read"):
        out["datasets_by_kind"] = _group(db, user, Dataset, Dataset.kind)
    if has_permission(user, "deploy:read"):
        out["deployments_by_status"] = _group(db, user, Deployment, Deployment.status)
    return out
