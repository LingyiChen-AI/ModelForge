from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.training import ModelVersion
from pydantic import BaseModel

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
def list_model_versions(db: Session = Depends(get_db)):
    return db.execute(select(ModelVersion).order_by(ModelVersion.id.desc())).scalars().all()
