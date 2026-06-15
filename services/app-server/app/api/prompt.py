from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.models.prompt import Prompt, PromptVersion
from app.schemas.prompt import (PromptOut, PromptDetailOut, PromptVersionOut,
                                PromptCreate, PromptVersionCreate,
                                PromptValidateIn, PromptValidateOut)
from app.services import prompt_service as svc
from app.pagination import paginate

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("", response_model=list[PromptOut])
def list_prompts(response: Response, page: int | None = Query(None, ge=1),
                 page_size: int = Query(20, ge=1, le=200),
                 _: User = Depends(require("prompt:read")), db: Session = Depends(get_db)):
    stmt = select(Prompt).order_by(Prompt.id.desc())
    return paginate(db, stmt, response, page, page_size)


@router.post("", response_model=PromptDetailOut, status_code=201)
def create_prompt(body: PromptCreate, user: User = Depends(require("prompt:write")),
                  db: Session = Depends(get_db)):
    try:
        return svc.create_prompt(db, name=body.name, system_prompt=body.system_prompt,
                                 user_prompt=body.user_prompt, note=body.note, created_by=user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/validate", response_model=PromptValidateOut)
def validate_prompt(body: PromptValidateIn, _: User = Depends(require("prompt:read"))):
    return svc.validate(body.system_prompt, body.user_prompt)


@router.get("/{prompt_id}", response_model=PromptDetailOut)
def get_prompt(prompt_id: int, _: User = Depends(require("prompt:read")),
               db: Session = Depends(get_db)):
    p = db.get(Prompt, prompt_id)
    if not p:
        raise HTTPException(404, "prompt not found")
    return p


@router.get("/{prompt_id}/versions", response_model=list[PromptVersionOut])
def list_versions(prompt_id: int, response: Response, page: int | None = Query(None, ge=1),
                  page_size: int = Query(20, ge=1, le=200),
                  _: User = Depends(require("prompt:read")), db: Session = Depends(get_db)):
    if not db.get(Prompt, prompt_id):
        raise HTTPException(404, "prompt not found")
    stmt = (select(PromptVersion).where(PromptVersion.prompt_id == prompt_id)
            .order_by(PromptVersion.version_no.desc()))
    return paginate(db, stmt, response, page, page_size)


@router.post("/{prompt_id}/versions", response_model=PromptVersionOut, status_code=201)
def add_version(prompt_id: int, body: PromptVersionCreate,
                user: User = Depends(require("prompt:write")), db: Session = Depends(get_db)):
    try:
        v = svc.add_version(db, prompt_id, system_prompt=body.system_prompt,
                            user_prompt=body.user_prompt, note=body.note, created_by=user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if v is None:
        raise HTTPException(404, "prompt not found")
    return v
