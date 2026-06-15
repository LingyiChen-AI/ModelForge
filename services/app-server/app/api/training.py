from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db import get_db
from app.authz import require, apply_scope
from app.auth import require_internal_token
from app.models.user import User
from app.models.training import TrainingJob
from app.schemas.training import TrainingJobCreate, TrainingJobOut
from app.services import training_service
from app.services.mlflow_sync import upsert_model_version_from_result
from app.services.delete_service import delete_training_job
from app.services.badcase_service import mark_fixed

router = APIRouter(prefix="/training-jobs", tags=["training"])

@router.post("", response_model=TrainingJobOut, status_code=201)
def create(body: TrainingJobCreate, user: User = Depends(require("training:run")),
           db: Session = Depends(get_db)):
    try:
        return training_service.create_and_dispatch(db, body, user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[TrainingJobOut])
def list_jobs(user: User = Depends(require("training:read")), db: Session = Depends(get_db)):
    return db.execute(apply_scope(select(TrainingJob).order_by(TrainingJob.id.desc()),
                                  TrainingJob, user)).scalars().all()

@router.get("/{job_id}", response_model=TrainingJobOut)
def get_job(job_id: int, user: User = Depends(require("training:read")),
            db: Session = Depends(get_db)):
    job = db.execute(apply_scope(select(TrainingJob).where(TrainingJob.id == job_id),
                                 TrainingJob, user)).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "not found")
    return job

@router.delete("/{job_id}")
def delete(job_id: int, cascade: bool = False, user: User = Depends(require("training:run")),
           db: Session = Depends(get_db)):
    job = db.execute(apply_scope(select(TrainingJob).where(TrainingJob.id == job_id),
                                 TrainingJob, user)).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "not found")
    delete_training_job(db, job_id, cascade)
    return {"deleted": True}

class TrainResultIn(BaseModel):
    run_id: str
    model_name: str
    version: str
    metrics: dict = {}
    badcase_fixes: list[int] = []   # ids of badcases this newly trained version now predicts correctly

@router.post("/internal/{job_id}/result", status_code=201,
             dependencies=[Depends(require_internal_token)])
def report_result(job_id: int, body: TrainResultIn, db: Session = Depends(get_db)):
    mv = upsert_model_version_from_result(db, job_id, body.model_dump())
    if body.badcase_fixes:
        mark_fixed(db, body.badcase_fixes, model_version_id=mv.id, version_label=mv.mlflow_version)
    return {"model_version_id": mv.id}
