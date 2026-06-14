from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.schemas.rbac import UserCreate, UserUpdate, UserOut, PasswordReset
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])

@router.post("", response_model=UserOut, status_code=201)
def create(body: UserCreate, _: User = Depends(require("user:manage")),
           db: Session = Depends(get_db)):
    try:
        return user_service.create_user(db, body)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("", response_model=list[UserOut])
def list_users(_: User = Depends(require("user:manage")), db: Session = Depends(get_db)):
    return db.execute(select(User).order_by(User.id)).scalars().all()

@router.patch("/{user_id}", response_model=UserOut)
def update(user_id: int, body: UserUpdate, _: User = Depends(require("user:manage")),
           db: Session = Depends(get_db)):
    try:
        return user_service.update_user(db, user_id, body)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except PermissionError as e:
        raise HTTPException(422, str(e))

@router.post("/{user_id}/reset-password", response_model=UserOut)
def reset_pw(user_id: int, body: PasswordReset, _: User = Depends(require("user:manage")),
             db: Session = Depends(get_db)):
    try:
        return user_service.reset_password(db, user_id, body.password)
    except ValueError as e:
        raise HTTPException(404, str(e))
