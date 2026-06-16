from sqlalchemy.orm import Session
from app.models.setting import AppSetting
from app.models.llm import LlmModel
from app.models.prompt_eval import PromptEvalRun
from app.ai_eval_defaults import DEFAULT_AI_EVAL_PROMPT
from app.celery_client import send_prompt_ai_eval_task   # module-level for monkeypatch

# 用户隔离:AI 评判系统指令按用户存,key 命名空间 ai_eval_prompt:<user_id>。
# 用户没改过 → 回落到代码默认 DEFAULT_AI_EVAL_PROMPT;改过 → 用用户自己的;可一键还原(删用户值)。
_PREFIX = "ai_eval_prompt:"


def _key(user_id: int) -> str:
    return f"{_PREFIX}{user_id}"


def get_prompt(db: Session, user_id: int) -> str:
    s = db.get(AppSetting, _key(user_id))
    return s.value if s and s.value else DEFAULT_AI_EVAL_PROMPT


def is_custom(db: Session, user_id: int) -> bool:
    s = db.get(AppSetting, _key(user_id))
    return bool(s and s.value)


def set_prompt(db: Session, user_id: int, value: str) -> None:
    k = _key(user_id)
    s = db.get(AppSetting, k)
    if s is None:
        db.add(AppSetting(key=k, value=value))
    else:
        s.value = value
    db.commit()


def reset_prompt(db: Session, user_id: int) -> None:
    """一键还原:删除该用户的自定义值,回落到默认。"""
    s = db.get(AppSetting, _key(user_id))
    if s is not None:
        db.delete(s)
        db.commit()


def dispatch(db: Session, run_id: int, model_id: int, user_id: int, concurrency: int = 20) -> None:
    run = db.get(PromptEvalRun, run_id)
    if run is None:
        raise ValueError("评测不存在")
    if db.get(LlmModel, model_id) is None:
        raise ValueError("评判模型无效")
    # 立刻标 running,让前端马上能看到「AI 评估中」+ 进度条;worker 再更新进度/最终状态
    run.ai_status = "running"
    run.ai_progress = 0.0
    run.ai_error = None
    db.commit()
    send_prompt_ai_eval_task(run_id, model_id, get_prompt(db, user_id), concurrency)
