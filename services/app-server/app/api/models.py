from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db import get_db
from app.authz import require, apply_scope
from app.models.user import User
from app.models.training import ModelVersion

class ModelVersionOut(BaseModel):
    id: int
    name: str
    mlflow_version: str
    task_type: str
    base_model: str
    train_metrics: dict
    stage: str
    class Config: from_attributes = True

router = APIRouter(prefix="/model-versions", tags=["models"])

@router.get("", response_model=list[ModelVersionOut])
def list_model_versions(user: User = Depends(require("model:read")), db: Session = Depends(get_db)):
    return db.execute(apply_scope(select(ModelVersion).order_by(ModelVersion.id.desc()),
                                  ModelVersion, user)).scalars().all()
