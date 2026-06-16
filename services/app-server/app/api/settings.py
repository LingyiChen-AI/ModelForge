from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.schemas.setting import AiEvalPromptOut, AiEvalPromptIn
from app.services import ai_eval_service

router = APIRouter(prefix="/settings", tags=["settings"])

# AI 评判系统指令是「谁做评测谁配自己的」→ 用 prompteval:annotate 鉴权(LLM 供应商配置仍是 llm:manage)。
_PERM = "prompteval:annotate"


def _out(db: Session, uid: int) -> AiEvalPromptOut:
    return AiEvalPromptOut(value=ai_eval_service.get_prompt(db, uid),
                           is_custom=ai_eval_service.is_custom(db, uid))


@router.get("/ai-eval-prompt", response_model=AiEvalPromptOut)
def get_ai_eval_prompt(user: User = Depends(require(_PERM)), db: Session = Depends(get_db)):
    return _out(db, user.id)


@router.put("/ai-eval-prompt", response_model=AiEvalPromptOut)
def put_ai_eval_prompt(body: AiEvalPromptIn, user: User = Depends(require(_PERM)),
                       db: Session = Depends(get_db)):
    ai_eval_service.set_prompt(db, user.id, body.value)
    return _out(db, user.id)


@router.delete("/ai-eval-prompt", response_model=AiEvalPromptOut)
def reset_ai_eval_prompt(user: User = Depends(require(_PERM)), db: Session = Depends(get_db)):
    """一键还原默认:删除当前用户的自定义值。"""
    ai_eval_service.reset_prompt(db, user.id)
    return _out(db, user.id)
