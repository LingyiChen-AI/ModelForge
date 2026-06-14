import io, pandas as pd
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require, apply_scope
from app.storage import build_storage
from app.models.user import User
from app.models.dataset import Dataset, DatasetVersion
from app.schemas.dataset import DatasetCreate, DatasetOut, DatasetVersionOut
from app.services.dataset_service import create_version

router = APIRouter(prefix="/datasets", tags=["datasets"])

def _get_owned_dataset(db: Session, dataset_id: int, user: User) -> Dataset:
    stmt = apply_scope(select(Dataset).where(Dataset.id == dataset_id), Dataset, user)
    ds = db.execute(stmt).scalar_one_or_none()
    if not ds:
        raise HTTPException(404, "dataset not found")
    return ds

@router.post("", response_model=DatasetOut, status_code=201)
def create_dataset(body: DatasetCreate, user: User = Depends(require("dataset:write")),
                   db: Session = Depends(get_db)):
    ds = Dataset(name=body.name, kind=body.kind.value, task_type=body.task_type.value,
                 created_by=user.id)
    db.add(ds); db.commit(); db.refresh(ds)
    return ds

@router.get("", response_model=list[DatasetOut])
def list_datasets(user: User = Depends(require("dataset:read")), db: Session = Depends(get_db)):
    return db.execute(apply_scope(select(Dataset), Dataset, user)).scalars().all()

def _read_upload(file: UploadFile) -> pd.DataFrame:
    raw = file.file.read()
    if file.filename.endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw))
    if file.filename.endswith(".jsonl"):
        return pd.read_json(io.BytesIO(raw), lines=True)
    raise HTTPException(400, "only .csv or .jsonl supported")

@router.post("/{dataset_id}/versions", response_model=DatasetVersionOut, status_code=201)
def upload_version(dataset_id: int, file: UploadFile = File(...), note: str = Form(""),
                   user: User = Depends(require("dataset:write")), db: Session = Depends(get_db)):
    ds = _get_owned_dataset(db, dataset_id, user)
    df = _read_upload(file)
    try:
        return create_version(db, build_storage(), ds, df, note)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("/{dataset_id}/versions", response_model=list[DatasetVersionOut])
def list_versions(dataset_id: int, user: User = Depends(require("dataset:read")),
                  db: Session = Depends(get_db)):
    _get_owned_dataset(db, dataset_id, user)
    return db.execute(select(DatasetVersion)
                      .where(DatasetVersion.dataset_id == dataset_id)
                      .order_by(DatasetVersion.version_no.desc())).scalars().all()
