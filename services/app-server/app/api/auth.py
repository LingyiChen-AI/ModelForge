from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.user import User
from app.auth import (verify_password, create_access_token, get_current_user,
                      permission_codes)
from app.schemas.auth import LoginRequest, LoginResponse, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])

def _user_info(user: User) -> UserInfo:
    return UserInfo(id=user.id, name=user.name, email=user.email,
                    role=user.role.name if user.role else None,
                    data_scope=user.role.data_scope if user.role else "own",
                    permissions=sorted(permission_codes(user)))

@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    return LoginResponse(access_token=create_access_token(user.id), user=_user_info(user))

@router.get("/me", response_model=UserInfo)
def me(user: User = Depends(get_current_user)):
    return _user_info(user)
