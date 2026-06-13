from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.training import EvalRun
from app.schemas.eval import EvalRunCreate, EvalRunOut
from app.services import eval_service

router = APIRouter(prefix="/eval-runs", tags=["eval"])

@router.post("", response_model=EvalRunOut, status_code=201)
def create(body: EvalRunCreate, db: Session = Depends(get_db)):
    try:
        return eval_service.create_and_dispatch(db, body)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[EvalRunOut])
def list_runs(dataset_version_id: int | None = None, db: Session = Depends(get_db)):
    q = select(EvalRun).order_by(EvalRun.id.desc())
    if dataset_version_id is not None:
        q = q.where(EvalRun.dataset_version_id == dataset_version_id)
    return db.execute(q).scalars().all()

@router.get("/{run_id}", response_model=EvalRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(EvalRun, run_id)
    if not run:
        raise HTTPException(404, "not found")
    return run
