from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.models.llm import LlmProvider
from app.schemas.llm import (ProviderCreate, ProviderUpdate, ProviderOut,
                             ModelAddIn, LlmModelOut, TestResult)
from app.services import llm_provider_service as svc
from app.pagination import paginate

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(response: Response, page: int | None = Query(None, ge=1),
                   page_size: int = Query(20, ge=1, le=200),
                   _: User = Depends(require("llm:manage")), db: Session = Depends(get_db)):
    stmt = select(LlmProvider).order_by(LlmProvider.id.desc())
    return paginate(db, stmt, response, page, page_size)


@router.post("/providers", response_model=ProviderOut, status_code=201)
def create_provider(body: ProviderCreate, user: User = Depends(require("llm:manage")),
                    db: Session = Depends(get_db)):
    return svc.create_provider(db, name=body.name, base_url=body.base_url,
                               api_key=body.api_key, model_ids=body.model_ids,
                               created_by=user.id)


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
def update_provider(provider_id: int, body: ProviderUpdate,
                    _: User = Depends(require("llm:manage")), db: Session = Depends(get_db)):
    p = svc.update_provider(db, provider_id, name=body.name, base_url=body.base_url,
                            enabled=body.enabled, api_key=body.api_key)
    if not p:
        raise HTTPException(404, "provider not found")
    return p


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: int, _: User = Depends(require("llm:manage")),
                    db: Session = Depends(get_db)):
    if not svc.delete_provider(db, provider_id):
        raise HTTPException(404, "provider not found")
    return {"deleted": True}


@router.post("/providers/{provider_id}/models", response_model=LlmModelOut, status_code=201)
def add_model(provider_id: int, body: ModelAddIn,
              _: User = Depends(require("llm:manage")), db: Session = Depends(get_db)):
    try:
        m = svc.add_model(db, provider_id, body.model_id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not m:
        raise HTTPException(404, "provider not found")
    return m


@router.delete("/models/{model_id}")
def remove_model(model_id: int, _: User = Depends(require("llm:manage")),
                 db: Session = Depends(get_db)):
    if not svc.remove_model(db, model_id):
        raise HTTPException(404, "model not found")
    return {"deleted": True}


@router.post("/models/{model_id}/test", response_model=TestResult)
def test_model(model_id: int, _: User = Depends(require("llm:manage")),
               db: Session = Depends(get_db)):
    result = svc.test_model(db, model_id)
    if result is None:
        raise HTTPException(404, "model not found")
    return result
