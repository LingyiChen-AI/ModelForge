from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth import get_current_user
from app.authz import has_permission, apply_scope
from app.models.user import User
from app.models.dataset import Dataset
from app.models.training import Model, TrainingJob, ModelVersion, EvalRun, Deployment
from app.models.prompt import Prompt
from app.models.prompt_eval import PromptEvalRun, PromptEvalItem

router = APIRouter(prefix="/stats", tags=["stats"])


def _count(db: Session, user: User, model, *conds) -> int:
    # apply_scope restricts to the user's data scope (own/all); conds add filters
    stmt = apply_scope(select(func.count()).select_from(model), model, user)
    for c in conds:
        stmt = stmt.where(c)
    return db.execute(stmt).scalar() or 0


def _item_count(db: Session, user: User, *conds) -> int:
    # PromptEvalItem 无 created_by → join run,按 run 的归属做数据范围
    stmt = apply_scope(
        select(func.count()).select_from(PromptEvalItem)
        .join(PromptEvalRun, PromptEvalRun.id == PromptEvalItem.run_id),
        PromptEvalRun, user)
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
    if has_permission(user, "prompt:read"):
        out["prompts"] = _count(db, user, Prompt)
    if has_permission(user, "prompteval:read"):
        out["prompt_eval_runs"] = _count(db, user, PromptEvalRun)
        out["prompt_eval_items"] = _item_count(db, user)
        out["prompt_human_evaluated"] = _item_count(db, user, PromptEvalItem.evaluated_at.is_not(None))
        out["prompt_ai_evaluated"] = _item_count(db, user, PromptEvalItem.ai_evaluated_at.is_not(None))
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
    if has_permission(user, "prompteval:read"):
        out["prompt_eval_runs_by_type"] = _group(db, user, PromptEvalRun, PromptEvalRun.eval_type)
    return out
