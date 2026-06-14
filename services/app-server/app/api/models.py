from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db import get_db
from app.authz import require, apply_scope
from app.models.user import User
from app.models.training import Model, ModelVersion, TrainingJob

TaskLiteral = Literal["classification", "ner", "pair", "embedding"]

class ModelVersionOut(BaseModel):
    id: int
    name: str
    model_id: int | None
    mlflow_version: str
    task_type: str
    base_model: str
    train_metrics: dict
    stage: str
    created_at: datetime
    created_by_name: str | None = None
    class Config: from_attributes = True

router = APIRouter(prefix="/model-versions", tags=["models"])

@router.get("", response_model=list[ModelVersionOut])
def list_model_versions(model_id: int | None = None,
                        user: User = Depends(require("model:read")), db: Session = Depends(get_db)):
    q = apply_scope(select(ModelVersion).order_by(ModelVersion.id.desc()), ModelVersion, user)
    if model_id is not None:
        q = q.where(ModelVersion.model_id == model_id)
    return db.execute(q).scalars().all()


# ---- model containers ----
class ModelCreate(BaseModel):
    name: str
    task_type: TaskLiteral
    description: str = ""

class ModelOut(BaseModel):
    id: int
    name: str
    task_type: str
    description: str
    version_count: int
    latest_version_id: int | None = None
    latest_version: str | None = None      # mlflow version label, e.g. "3"
    latest_metrics: dict = {}
    latest_stage: str | None = None
    created_at: datetime
    created_by_name: str | None = None

def _model_out(m: Model, db: Session) -> ModelOut:
    versions = db.execute(
        select(ModelVersion).where(ModelVersion.model_id == m.id)
        .order_by(ModelVersion.id.desc())).scalars().all()
    latest = versions[0] if versions else None
    return ModelOut(
        id=m.id, name=m.name, task_type=m.task_type, description=m.description,
        version_count=len(versions),
        latest_version_id=latest.id if latest else None,
        latest_version=latest.mlflow_version if latest else None,
        latest_metrics=latest.train_metrics if latest else {},
        latest_stage=latest.stage if latest else None,
        created_at=m.created_at, created_by_name=m.created_by_name)

class ModelTrainingOut(BaseModel):
    """One training run under a model, for the model-detail history timeline."""
    id: int
    name: str
    status: str
    created_at: datetime
    created_by_name: str | None = None
    train_count: int          # number of train-set versions merged
    eval_count: int           # number of eval-set versions merged
    train_datasets: list[str] = []
    eval_datasets: list[str] = []
    version_label: str | None = None   # mlflow version produced by this run, if any
    metrics: dict = {}                 # the produced version's train metrics

models_router = APIRouter(prefix="/models", tags=["models"])

@models_router.get("", response_model=list[ModelOut])
def list_models(user: User = Depends(require("model:read")), db: Session = Depends(get_db)):
    models = db.execute(apply_scope(select(Model).order_by(Model.id.desc()), Model, user)).scalars().all()
    return [_model_out(m, db) for m in models]

@models_router.get("/{model_id}/trainings", response_model=list[ModelTrainingOut])
def model_trainings(model_id: int, user: User = Depends(require("model:read")),
                    db: Session = Depends(get_db)):
    m = db.execute(apply_scope(select(Model).where(Model.id == model_id), Model, user)).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "model not found")
    jobs = db.execute(select(TrainingJob).where(TrainingJob.model_id == model_id)
                      .order_by(TrainingJob.id.desc())).scalars().all()
    # map each job to the model version it produced (for the result metrics + label)
    by_job = {v.source_training_job_id: v for v in db.execute(
        select(ModelVersion).where(ModelVersion.model_id == model_id)).scalars()}
    out = []
    for j in jobs:
        v = by_job.get(j.id)
        out.append(ModelTrainingOut(
            id=j.id, name=j.name, status=j.status, created_at=j.created_at,
            created_by_name=j.created_by_name,
            train_count=len(j.train_version_ids), eval_count=len(j.eval_version_ids),
            train_datasets=j.train_datasets, eval_datasets=j.eval_datasets,
            version_label=v.mlflow_version if v else None,
            metrics=v.train_metrics if v else {}))
    return out

@models_router.post("", response_model=ModelOut, status_code=201)
def create_model(body: ModelCreate, user: User = Depends(require("model:write")),
                 db: Session = Depends(get_db)):
    if db.execute(select(Model).where(Model.name == body.name)).first():
        raise HTTPException(409, "模型名已存在")
    m = Model(name=body.name, task_type=body.task_type, description=body.description, created_by=user.id)
    db.add(m); db.commit(); db.refresh(m)
    return _model_out(m, db)

@models_router.delete("/{model_id}")
def delete_model_ep(model_id: int, cascade: bool = False, user: User = Depends(require("model:write")),
                    db: Session = Depends(get_db)):
    from app.services.delete_service import delete_model
    m = db.execute(apply_scope(select(Model).where(Model.id == model_id), Model, user)).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "model not found")
    delete_model(db, model_id, cascade)
    return {"deleted": True}

class StageUpdate(BaseModel):
    stage: Literal["none", "staging", "prod", "archived"]

@router.patch("/{mv_id}", response_model=ModelVersionOut)
def set_stage(mv_id: int, body: StageUpdate, user: User = Depends(require("model:write")),
              db: Session = Depends(get_db)):
    mv = db.execute(apply_scope(select(ModelVersion).where(ModelVersion.id == mv_id),
                                ModelVersion, user)).scalar_one_or_none()
    if not mv:
        raise HTTPException(404, "model version not found")
    mv.stage = body.stage
    db.commit(); db.refresh(mv)
    return mv
