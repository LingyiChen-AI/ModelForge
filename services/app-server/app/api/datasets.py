import io, pandas as pd
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from modelforge_common.enums import TaskType
from app.db import get_db
from app.authz import require, apply_scope
from app.storage import build_storage
from app.models.user import User
from app.models.dataset import Dataset, DatasetVersion
from app.schemas.dataset import DatasetCreate, DatasetOut, DatasetVersionOut, DatasetTreeOut
from app.schemas.prompt import PromptDatasetCreate
from app.services.dataset_service import create_version, serialize_template, serialize_df
from app.pagination import paginate

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

@router.post("/prompt", response_model=DatasetOut, status_code=201)
def create_prompt_dataset(body: PromptDatasetCreate,
                          user: User = Depends(require("dataset:write")),
                          db: Session = Depends(get_db)):
    ds = Dataset(name=body.name, kind="prompt", task_type="prompt", created_by=user.id)
    db.add(ds); db.commit(); db.refresh(ds)
    return ds

@router.get("", response_model=list[DatasetOut])
def list_datasets(response: Response, page: int | None = Query(None, ge=1),
                  page_size: int = Query(20, ge=1, le=200),
                  user: User = Depends(require("dataset:read")), db: Session = Depends(get_db)):
    stmt = apply_scope(select(Dataset).order_by(Dataset.id.desc()), Dataset, user)
    return paginate(db, stmt, response, page, page_size)


@router.get("/tree", response_model=list[DatasetTreeOut])
def dataset_tree(kind: str | None = None, user: User = Depends(require("dataset:read")),
                 db: Session = Depends(get_db)):
    """Datasets + their versions in ONE call (2 queries), for cascade/version pickers.
    Replaces the frontend's N+1 (one /versions request per dataset)."""
    stmt = apply_scope(select(Dataset).order_by(Dataset.id.desc()), Dataset, user)
    if kind:
        stmt = stmt.where(Dataset.kind == kind)
    datasets = list(db.execute(stmt).scalars())
    by_ds: dict[int, list] = {}
    if datasets:
        ids = [d.id for d in datasets]
        for v in db.execute(select(DatasetVersion).where(DatasetVersion.dataset_id.in_(ids))
                            .order_by(DatasetVersion.version_no.desc())).scalars():
            by_ds.setdefault(v.dataset_id, []).append(v)
    return [DatasetTreeOut(id=d.id, name=d.name, kind=d.kind, task_type=d.task_type,
                           versions=by_ds.get(d.id, [])) for d in datasets]

def _read_upload(file: UploadFile) -> pd.DataFrame:
    raw = file.file.read()
    name = (file.filename or "").lower()
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw))
    if name.endswith(".jsonl"):
        return pd.read_json(io.BytesIO(raw), lines=True)
    if name.endswith(".xlsx"):
        return pd.read_excel(io.BytesIO(raw))
    raise HTTPException(400, "only .csv, .jsonl or .xlsx supported")


def _template_response(task_type: TaskType, fmt: str, filename_stem: str) -> Response:
    if fmt not in ("csv", "jsonl", "xlsx"):
        raise HTTPException(400, "fmt must be csv | jsonl | xlsx")
    content, media_type, ext = serialize_template(task_type, fmt)
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename_stem}.{ext}"'})


@router.get("/template")
def download_template_by_type(task_type: str, fmt: str = "csv",
                              _: User = Depends(require("dataset:read"))):
    try:
        tt = TaskType(task_type)
    except ValueError:
        raise HTTPException(400, f"invalid task_type: {task_type}")
    return _template_response(tt, fmt, f"{task_type}-template")


@router.get("/{dataset_id}/template")
def download_template(dataset_id: int, fmt: str = "csv",
                      user: User = Depends(require("dataset:read")),
                      db: Session = Depends(get_db)):
    ds = _get_owned_dataset(db, dataset_id, user)
    return _template_response(TaskType(ds.task_type), fmt, f"dataset-{dataset_id}-template")

@router.post("/{dataset_id}/versions", response_model=DatasetVersionOut, status_code=201)
def upload_version(dataset_id: int, file: UploadFile = File(...), note: str = Form(""),
                   user: User = Depends(require("dataset:write")), db: Session = Depends(get_db)):
    ds = _get_owned_dataset(db, dataset_id, user)
    df = _read_upload(file)
    try:
        return create_version(db, build_storage(), ds, df, note, created_by=user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("/{dataset_id}/versions", response_model=list[DatasetVersionOut])
def list_versions(dataset_id: int, response: Response,
                  page: int | None = Query(None, ge=1),
                  page_size: int = Query(20, ge=1, le=200),
                  user: User = Depends(require("dataset:read")),
                  db: Session = Depends(get_db)):
    _get_owned_dataset(db, dataset_id, user)
    stmt = (select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_no.desc()))
    return paginate(db, stmt, response, page, page_size)


@router.get("/{dataset_id}/versions/{version_id}/download")
def download_version(dataset_id: int, version_id: int, fmt: str = "csv",
                     user: User = Depends(require("dataset:read")), db: Session = Depends(get_db)):
    ds = _get_owned_dataset(db, dataset_id, user)
    ver = db.execute(select(DatasetVersion).where(
        DatasetVersion.id == version_id, DatasetVersion.dataset_id == dataset_id)).scalar_one_or_none()
    if not ver:
        raise HTTPException(404, "version not found")
    if fmt not in ("csv", "jsonl", "xlsx"):
        raise HTTPException(400, "fmt must be csv | jsonl | xlsx")
    df = build_storage().read_snapshot(ver.storage_uri)
    content, media_type, ext = serialize_df(df, TaskType(ds.task_type), fmt)
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="dataset-{dataset_id}-v{ver.version_no}.{ext}"'})
