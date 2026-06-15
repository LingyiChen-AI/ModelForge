import random
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.models.prompt import PromptVersion
from app.models.dataset import Dataset, DatasetVersion
from app.models.llm import LlmModel, LlmProvider
from app.models.prompt_eval import PromptEvalRun, PromptEvalArm, PromptEvalItem
from app.schemas.prompt_eval import PromptEvalCreate, PromptEvalOut, PromptEvalDetailOut, ItemOut, VerdictIn, OutputOut, AiEvaluateIn
from app.services import prompt_eval_service as svc
from app.services import prompt_eval_stats
from app.services import ai_eval_service
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
def list_items(run_id: int, response: Response, bucket: str = "all",
               page: int | None = Query(None, ge=1), page_size: int = Query(20, ge=1, le=200),
               _: User = Depends(require("prompteval:read")), db: Session = Depends(get_db)):
    if not db.get(PromptEvalRun, run_id):
        raise HTTPException(404, "run not found")
    stmt = select(PromptEvalItem).where(PromptEvalItem.run_id == run_id)
    if bucket == "pending":
        stmt = stmt.where(PromptEvalItem.evaluated_at.is_(None))
    elif bucket == "evaluated":
        stmt = stmt.where(PromptEvalItem.evaluated_at.is_not(None))
    stmt = stmt.order_by(PromptEvalItem.item_index)
    items = paginate(db, stmt, response, page, page_size)
    out = []
    for it in items:
        shuffled = list(it.outputs)
        random.Random(it.id).shuffle(shuffled)
        out.append(ItemOut(
            id=it.id, item_index=it.item_index, dataset_version_id=it.dataset_version_id,
            row_index=it.row_index, inputs=it.inputs,
            outputs=[OutputOut.model_validate(o) for o in shuffled],
            winner_arm_id=it.winner_arm_id, all_bad=it.all_bad, is_good=it.is_good,
            annotated_by_name=it.annotated_by_name, evaluated_at=it.evaluated_at,
            ai_winner_arm_id=it.ai_winner_arm_id, ai_all_bad=it.ai_all_bad, ai_is_good=it.ai_is_good,
            ai_model_id=it.ai_model_id, ai_reasoning=it.ai_reasoning, ai_evaluated_at=it.ai_evaluated_at,
        ))
    return out


@router.patch("/items/{item_id}/verdict", response_model=ItemOut)
def submit_verdict(item_id: int, body: VerdictIn,
                   user: User = Depends(require("prompteval:annotate")), db: Session = Depends(get_db)):
    try:
        item = svc.submit_verdict(db, item_id, body, user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if item is None:
        raise HTTPException(404, "item not found")
    return ItemOut(
        id=item.id, item_index=item.item_index, dataset_version_id=item.dataset_version_id,
        row_index=item.row_index, inputs=item.inputs,
        outputs=[OutputOut.model_validate(o) for o in item.outputs],
        winner_arm_id=item.winner_arm_id, all_bad=item.all_bad, is_good=item.is_good,
        annotated_by_name=item.annotated_by_name, evaluated_at=item.evaluated_at,
        ai_winner_arm_id=item.ai_winner_arm_id, ai_all_bad=item.ai_all_bad, ai_is_good=item.ai_is_good,
        ai_model_id=item.ai_model_id, ai_reasoning=item.ai_reasoning, ai_evaluated_at=item.ai_evaluated_at,
    )


@router.post("/{run_id}/ai-evaluate")
def ai_evaluate(run_id: int, body: AiEvaluateIn,
                _: User = Depends(require("prompteval:annotate")), db: Session = Depends(get_db)):
    try:
        ai_eval_service.dispatch(db, run_id, body.model_id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"dispatched": True}


@router.get("/{run_id}/stats")
def get_stats(run_id: int, _: User = Depends(require("prompteval:read")), db: Session = Depends(get_db)):
    s = prompt_eval_stats.stats(db, run_id)
    if s is None:
        raise HTTPException(404, "run not found")
    return s
