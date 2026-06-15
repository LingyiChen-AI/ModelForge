import time
from sqlalchemy import select
from sqlalchemy.orm import Session
from modelforge_common.llm_client import chat as llm_chat, LLMError
from app.models.llm import LlmProvider, LlmModel

PROBE = [{"role": "user", "content": "1+1=? 只回答数字"}]


def create_provider(db: Session, *, name: str, base_url: str, api_key: str,
                    model_ids: list[str], created_by: int | None) -> LlmProvider:
    p = LlmProvider(name=name, base_url=base_url, api_key=api_key, created_by=created_by)
    for mid in dict.fromkeys(model_ids):          # 去重并保序
        p.models.append(LlmModel(model_id=mid))
    db.add(p); db.commit(); db.refresh(p)
    return p


def update_provider(db: Session, provider_id: int, *, name: str | None = None,
                    base_url: str | None = None, enabled: bool | None = None,
                    api_key: str | None = None) -> LlmProvider | None:
    p = db.get(LlmProvider, provider_id)
    if not p:
        return None
    if name is not None:
        p.name = name
    if base_url is not None:
        p.base_url = base_url
    if enabled is not None:
        p.enabled = enabled
    if api_key:                                   # 留空/None -> 保留原 key
        p.api_key = api_key
    db.commit(); db.refresh(p)
    return p


def delete_provider(db: Session, provider_id: int) -> bool:
    p = db.get(LlmProvider, provider_id)
    if not p:
        return False
    db.delete(p); db.commit()                     # cascade delete-orphan 清 models
    return True


def add_model(db: Session, provider_id: int, model_id: str) -> LlmModel | None:
    p = db.get(LlmProvider, provider_id)
    if not p:
        return None
    dup = db.execute(select(LlmModel).where(
        LlmModel.provider_id == provider_id, LlmModel.model_id == model_id)).scalar_one_or_none()
    if dup:
        raise ValueError("该供应商下已存在同名 model_id")
    m = LlmModel(provider_id=provider_id, model_id=model_id)
    db.add(m); db.commit(); db.refresh(m)
    return m


def remove_model(db: Session, model_pk: int) -> bool:
    m = db.get(LlmModel, model_pk)
    if not m:
        return False
    db.delete(m); db.commit()
    return True


def test_model(db: Session, model_pk: int) -> dict | None:
    m = db.get(LlmModel, model_pk)
    if not m:
        return None
    p = m.provider
    t0 = time.monotonic()
    try:
        res = llm_chat(p.base_url, p.api_key, m.model_id, PROBE)
        return {"ok": True, "reply": res.content,
                "latency_ms": int((time.monotonic() - t0) * 1000), "error": None}
    except LLMError as e:
        return {"ok": False, "reply": None,
                "latency_ms": int((time.monotonic() - t0) * 1000), "error": e.message}
