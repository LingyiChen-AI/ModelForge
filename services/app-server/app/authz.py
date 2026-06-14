from fastapi import Depends, HTTPException
from app.auth import get_current_user, permission_codes
from app.models.user import User


def has_permission(user: User, code: str) -> bool:
    codes = permission_codes(user)
    return "*" in codes or code in codes


def require(code: str):
    def dep(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, code):
            raise HTTPException(403, f"permission denied: {code}")
        return user
    return dep


def effective_scope(user: User) -> str:
    if "*" in permission_codes(user):
        return "all"
    return user.role.data_scope if user.role else "own"


def apply_scope(stmt, model, user: User):
    if effective_scope(user) == "own":
        return stmt.where(model.created_by == user.id)
    return stmt
