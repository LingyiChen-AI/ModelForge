from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.training import TrainingJob
from app.schemas.training import TrainingJobCreate, TrainingJobOut
from app.services import training_service

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

@router.get("/{job_id}", response_model=TrainingJobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(TrainingJob, job_id)
    if not job:
        raise HTTPException(404, "not found")
    return job
