from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.services import api_key_service
from app.models.api_key import ApiKey


def require_api_key(scope: str):
    def dep(x_api_key: str | None = Header(default=None),
            db: Session = Depends(get_db)) -> ApiKey:
        key = api_key_service.verify(db, x_api_key or "", scope)
        if not key:
            raise HTTPException(401, "missing or invalid api key")
        return key
    return dep
