from sqlalchemy.orm import Session
from app.models.setting import AppSetting
from app.models.llm import LlmModel
from app.models.prompt_eval import PromptEvalRun
from app.ai_eval_defaults import DEFAULT_AI_EVAL_PROMPT
from app.celery_client import send_prompt_ai_eval_task   # module-level for monkeypatch

_KEY = "ai_eval_prompt"


def get_prompt(db: Session) -> str:
    s = db.get(AppSetting, _KEY)
    return s.value if s and s.value else DEFAULT_AI_EVAL_PROMPT


def set_prompt(db: Session, value: str) -> None:
    s = db.get(AppSetting, _KEY)
    if s is None:
        s = AppSetting(key=_KEY, value=value)
        db.add(s)
    else:
        s.value = value
    db.commit()


def dispatch(db: Session, run_id: int, model_id: int) -> None:
    if db.get(PromptEvalRun, run_id) is None:
        raise ValueError("评测不存在")
    if db.get(LlmModel, model_id) is None:
        raise ValueError("评判模型无效")
    send_prompt_ai_eval_task(run_id, model_id, get_prompt(db))
