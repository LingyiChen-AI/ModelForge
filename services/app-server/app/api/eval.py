from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require, apply_scope
from app.models.user import User
from app.models.training import EvalRun
from app.schemas.eval import EvalRunCreate, EvalRunOut
from app.services import eval_service, delete_service, export_service
from app.pagination import paginate

router = APIRouter(prefix="/eval-runs", tags=["eval"])

@router.post("", response_model=EvalRunOut, status_code=201)
def create(body: EvalRunCreate, user: User = Depends(require("eval:run")),
           db: Session = Depends(get_db)):
    try:
        return eval_service.create_and_dispatch(db, body, user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[EvalRunOut])
def list_runs(response: Response, page: int | None = Query(None, ge=1),
              page_size: int = Query(20, ge=1, le=200),
              dataset_version_id: int | None = None,
              user: User = Depends(require("eval:read")), db: Session = Depends(get_db)):
    stmt = apply_scope(select(EvalRun).order_by(EvalRun.id.desc()), EvalRun, user)
    if dataset_version_id is not None:
        stmt = stmt.where(EvalRun.dataset_version_id == dataset_version_id)
    return paginate(db, stmt, response, page, page_size)

@router.get("/{run_id}", response_model=EvalRunOut)
def get_run(run_id: int, user: User = Depends(require("eval:read")),
            db: Session = Depends(get_db)):
    run = db.execute(apply_scope(select(EvalRun).where(EvalRun.id == run_id),
                                 EvalRun, user)).scalar_one_or_none()
    if not run:
        raise HTTPException(404, "not found")
    return run

@router.get("/{run_id}/predictions.xlsx")
def export_predictions(run_id: int, user: User = Depends(require("eval:read")),
                       db: Session = Depends(get_db)):
    run = db.execute(apply_scope(select(EvalRun).where(EvalRun.id == run_id),
                                 EvalRun, user)).scalar_one_or_none()
    if not run:
        raise HTTPException(404, "not found")
    if not run.predictions:
        raise HTTPException(409, "该测试无逐条预测数据(请重新发起测试)")
    data = export_service.eval_predictions_xlsx(run)
    return Response(content=data, media_type=export_service.XLSX_MEDIA,
                    headers={"Content-Disposition": f'attachment; filename="eval_{run_id}_predictions.xlsx"'})


@router.delete("/{run_id}", status_code=204)
def delete_run(run_id: int, user: User = Depends(require("eval:run")),
               db: Session = Depends(get_db)):
    # ownership / scope check before delete
    run = db.execute(apply_scope(select(EvalRun).where(EvalRun.id == run_id),
                                 EvalRun, user)).scalar_one_or_none()
    if not run:
        raise HTTPException(404, "not found")
    delete_service.delete_eval_run(db, run_id)
