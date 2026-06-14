from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.schemas.api_key import ApiKeyCreate, ApiKeyOut, ApiKeyCreated, VALID_SCOPES
from app.services import api_key_service

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("", response_model=list[ApiKeyOut])
def list_keys(_: User = Depends(require("apikey:manage")), db: Session = Depends(get_db)):
    return api_key_service.list_keys(db)


@router.post("", response_model=ApiKeyCreated, status_code=201)
def create_key(body: ApiKeyCreate, user: User = Depends(require("apikey:manage")),
               db: Session = Depends(get_db)):
    bad = [s for s in body.scopes if s not in VALID_SCOPES]
    if bad or not body.scopes:
        raise HTTPException(422, f"scopes must be a non-empty subset of {sorted(VALID_SCOPES)}")
    plaintext, key = api_key_service.create_key(db, name=body.name, scopes=body.scopes,
                                                created_by=user.id)
    out = ApiKeyOut.model_validate(key)
    return ApiKeyCreated(**out.model_dump(), plaintext=plaintext)


@router.delete("/{key_id}")
def revoke_key(key_id: int, _: User = Depends(require("apikey:manage")),
               db: Session = Depends(get_db)):
    if not api_key_service.revoke(db, key_id):
        raise HTTPException(404, "key not found or already revoked")
    return {"revoked": True}
