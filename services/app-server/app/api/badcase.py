from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.api_key_auth import require_api_key
from app.models.user import User
from app.models.api_key import ApiKey
from app.models.badcase import Badcase
from app import badcase_contracts as bc
from app.schemas.badcase import BadcaseReportIn, BadcaseAnnotateIn, BuildDatasetIn, BadcaseOut, BadcaseSummaryOut
from app.services import badcase_service
from app.pagination import paginate

router = APIRouter(tags=["badcase"])


@router.post("/badcase/report", response_model=BadcaseOut, status_code=201)
def report(body: BadcaseReportIn, key: ApiKey = Depends(require_api_key("badcase:report")),
           db: Session = Depends(get_db)):
    try:
        return badcase_service.report(db, body, source=key.name)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/badcase/rules")
def rules(_: User = Depends(require("badcase:read"))):
    return {"rules": bc.rules()}


@router.get("/badcases", response_model=list[BadcaseOut])
def list_badcases(response: Response, page: int | None = Query(None, ge=1),
                  page_size: int = Query(20, ge=1, le=200),
                  model_version_id: int | None = None, status: str | None = None,
                  category: str | None = None, _: User = Depends(require("badcase:read")),
                  db: Session = Depends(get_db)):
    stmt = select(Badcase).order_by(Badcase.id.desc())
    if model_version_id is not None:
        stmt = stmt.where(Badcase.model_version_id == model_version_id)
    if status:
        stmt = stmt.where(Badcase.status == status)
    if category:
        stmt = stmt.where(Badcase.category == category)
    return paginate(db, stmt, response, page, page_size)


@router.get("/badcases/summary", response_model=list[BadcaseSummaryOut])
def badcase_summary(_: User = Depends(require("badcase:read")), db: Session = Depends(get_db)):
    return badcase_service.summary(db)


@router.get("/badcases/stats")
def badcase_stats(_: User = Depends(require("badcase:read")), db: Session = Depends(get_db)):
    """Overview aggregate (total / processed / pending / fixed / fix_rate)."""
    return badcase_service.stats(db)


@router.get("/badcases/labels")
def badcase_labels(model_version_id: int, _: User = Depends(require("badcase:read")),
                   db: Session = Depends(get_db)):
    """Candidate annotation labels for a model version (for the annotation dropdown)."""
    try:
        return {"labels": badcase_service.label_options(db, model_version_id)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/badcases/{case_id}", response_model=BadcaseOut)
def get_badcase(case_id: int, _: User = Depends(require("badcase:read")),
                db: Session = Depends(get_db)):
    case = db.get(Badcase, case_id)
    if not case:
        raise HTTPException(404, "not found")
    return case


@router.patch("/badcases/{case_id}/annotate", response_model=BadcaseOut)
def annotate(case_id: int, body: BadcaseAnnotateIn, user: User = Depends(require("badcase:annotate")),
             db: Session = Depends(get_db)):
    if not db.get(Badcase, case_id):
        raise HTTPException(404, "not found")
    try:
        return badcase_service.annotate(db, case_id, body.annotation, user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/badcases/build-dataset", status_code=201)
def build_dataset(body: BuildDatasetIn, user: User = Depends(require("dataset:write")),
                  db: Session = Depends(get_db)):
    try:
        ds, version = badcase_service.build_dataset(db, body.badcase_ids, body.name, user.id)
        return {"dataset_id": ds.id, "dataset_name": ds.name,
                "version_id": version.id, "version_no": version.version_no, "row_count": version.row_count}
    except ValueError as e:
        raise HTTPException(422, str(e))
