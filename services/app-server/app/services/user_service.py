from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.rbac import Role
from app.auth import hash_password

SUPERADMIN = "superadmin"

def _superadmin_role_id(db: Session):
    r = db.execute(select(Role).where(Role.name == SUPERADMIN)).scalar_one_or_none()
    return r.id if r else None

def _active_superadmin_count(db: Session) -> int:
    sid = _superadmin_role_id(db)
    if sid is None:
        return 0
    return db.execute(select(func.count()).select_from(User)
                      .where(User.role_id == sid, User.is_active.is_(True))).scalar()

def create_user(db: Session, body) -> User:
    if db.execute(select(User).where(User.email == body.email)).scalar_one_or_none():
        raise ValueError("email already exists")
    u = User(name=body.name, email=body.email,
             password_hash=hash_password(body.password), role_id=body.role_id, is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u

def update_user(db: Session, user_id: int, body) -> User:
    u = db.get(User, user_id)
    if not u:
        raise ValueError("user not found")
    sid = _superadmin_role_id(db)
    last_admin = (u.role_id == sid and u.is_active and _active_superadmin_count(db) == 1)
    if last_admin and (body.is_active is False or
                       (body.role_id is not None and body.role_id != sid)):
        raise PermissionError("cannot demote or deactivate the last superadmin")
    if body.role_id is not None:
        u.role_id = body.role_id
    if body.is_active is not None:
        u.is_active = body.is_active
    db.commit(); db.refresh(u)
    return u

def reset_password(db: Session, user_id: int, password: str) -> User:
    u = db.get(User, user_id)
    if not u:
        raise ValueError("user not found")
    u.password_hash = hash_password(password); db.commit(); db.refresh(u)
    return u
