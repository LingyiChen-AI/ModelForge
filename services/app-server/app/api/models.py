from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db import get_db
from app.authz import require, apply_scope
from app.models.user import User
from app.models.training import Model, ModelVersion

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

models_router = APIRouter(prefix="/models", tags=["models"])

@models_router.get("", response_model=list[ModelOut])
def list_models(user: User = Depends(require("model:read")), db: Session = Depends(get_db)):
    models = db.execute(apply_scope(select(Model).order_by(Model.id.desc()), Model, user)).scalars().all()
    return [_model_out(m, db) for m in models]

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
