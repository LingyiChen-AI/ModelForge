from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.training import TrainingJob
from app.schemas.training import TrainingJobCreate, TrainingJobOut
from app.services import training_service
from app.services.mlflow_sync import upsert_model_version_from_result
from pydantic import BaseModel

router = APIRouter(prefix="/training-jobs", tags=["training"])

@router.post("", response_model=TrainingJobOut, status_code=201)
def create(body: TrainingJobCreate, db: Session = Depends(get_db)):
    try:
        return training_service.create_and_dispatch(db, body)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[TrainingJobOut])
def list_jobs(db: Session = Depends(get_db)):
    return db.execute(select(TrainingJob).order_by(TrainingJob.id.desc())).scalars().all()

class TrainResultIn(BaseModel):
    run_id: str
    model_name: str
    version: str
    metrics: dict = {}

@router.post("/internal/{job_id}/result", status_code=201)
def report_result(job_id: int, body: TrainResultIn, db: Session = Depends(get_db)):
    mv = upsert_model_version_from_result(db, job_id, body.model_dump())
    return {"model_version_id": mv.id}

@router.get("/{job_id}", response_model=TrainingJobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, "not found")
    return job
