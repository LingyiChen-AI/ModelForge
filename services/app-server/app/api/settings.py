from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.schemas.setting import AiEvalPromptOut, AiEvalPromptIn
from app.services import ai_eval_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/ai-eval-prompt", response_model=AiEvalPromptOut)
def get_ai_eval_prompt(_: User = Depends(require("llm:manage")), db: Session = Depends(get_db)):
    return AiEvalPromptOut(value=ai_eval_service.get_prompt(db))


@router.put("/ai-eval-prompt", response_model=AiEvalPromptOut)
def put_ai_eval_prompt(body: AiEvalPromptIn, _: User = Depends(require("llm:manage")),
                       db: Session = Depends(get_db)):
    ai_eval_service.set_prompt(db, body.value)
    return AiEvalPromptOut(value=ai_eval_service.get_prompt(db))
