from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.models.prompt import PromptVersion
from app.models.dataset import Dataset, DatasetVersion
from app.models.llm import LlmModel, LlmProvider
from app.models.prompt_eval import PromptEvalRun, PromptEvalItem
from app.schemas.prompt_eval import PromptEvalCreate, PromptEvalOut, PromptEvalDetailOut, ItemOut
from app.services import prompt_eval_service as svc
from app.pagination import paginate

router = APIRouter(prefix="/prompt-evals", tags=["prompt-evals"])


@router.get("", response_model=list[PromptEvalOut])
def list_runs(response: Response, page: int | None = Query(None, ge=1),
              page_size: int = Query(20, ge=1, le=200),
              _: User = Depends(require("prompteval:read")), db: Session = Depends(get_db)):
    stmt = select(PromptEvalRun).order_by(PromptEvalRun.id.desc())
    return paginate(db, stmt, response, page, page_size)


@router.get("/options")
def eval_options(_: User = Depends(require("prompteval:read")), db: Session = Depends(get_db)):
    pvs = db.execute(select(PromptVersion)
                     .order_by(PromptVersion.prompt_id, PromptVersion.version_no.desc())).scalars().all()
    prompt_versions = [{"id": pv.id, "label": f"{pv.prompt.name} V{pv.version_no}"} for pv in pvs]
    models = [{"id": m.id, "label": f"{m.model_id} · {p.name}"}
              for m, p in db.execute(
                  select(LlmModel, LlmProvider).join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                  .where(LlmProvider.enabled.is_(True))).all()]
    pds = [{"version_id": dv.id, "label": f"{dv.dataset.name} V{dv.version_no}"}
           for dv in db.execute(
               select(DatasetVersion).join(Dataset, Dataset.id == DatasetVersion.dataset_id)
               .where(Dataset.kind == "prompt").order_by(DatasetVersion.id.desc())).scalars().all()]
    return {"prompt_versions": prompt_versions, "models": models, "prompt_datasets": pds}


@router.post("", response_model=PromptEvalDetailOut, status_code=201)
def create_run(body: PromptEvalCreate, user: User = Depends(require("prompteval:run")),
               db: Session = Depends(get_db)):
    try:
        return svc.create_and_dispatch(db, body, created_by=user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/{run_id}", response_model=PromptEvalDetailOut)
def get_run(run_id: int, _: User = Depends(require("prompteval:read")), db: Session = Depends(get_db)):
    run = db.get(PromptEvalRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return run


@router.get("/{run_id}/items", response_model=list[ItemOut])
def list_items(run_id: int, response: Response, page: int | None = Query(None, ge=1),
               page_size: int = Query(20, ge=1, le=200),
               _: User = Depends(require("prompteval:read")), db: Session = Depends(get_db)):
    if not db.get(PromptEvalRun, run_id):
        raise HTTPException(404, "run not found")
    stmt = (select(PromptEvalItem).where(PromptEvalItem.run_id == run_id)
            .order_by(PromptEvalItem.item_index))
    return paginate(db, stmt, response, page, page_size)
