from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.rbac import Role, Permission
from app.models.user import User

def _perms(db: Session, codes):
    found = db.execute(select(Permission).where(Permission.code.in_(codes))).scalars().all()
    known = {p.code for p in found}
    missing = set(codes) - known
    if missing:
        raise ValueError(f"unknown permission codes: {sorted(missing)}")
    return found

def create_role(db: Session, body) -> Role:
    if db.execute(select(Role).where(Role.name == body.name)).scalar_one_or_none():
        raise ValueError("role name exists")
    r = Role(name=body.name, description=body.description, data_scope=body.data_scope,
             is_system=False, permissions=_perms(db, body.permission_codes))
    db.add(r); db.commit(); db.refresh(r)
    return r

def update_role(db: Session, role_id: int, body) -> Role:
    r = db.get(Role, role_id)
    if not r:
        raise ValueError("role not found")
    if r.is_system:
        raise PermissionError("system role is immutable")
    if body.description is not None:
        r.description = body.description
    if body.data_scope is not None:
        r.data_scope = body.data_scope
    if body.permission_codes is not None:
        r.permissions = _perms(db, body.permission_codes)
    db.commit(); db.refresh(r)
    return r

def delete_role(db: Session, role_id: int) -> None:
    r = db.get(Role, role_id)
    if not r:
        raise ValueError("role not found")
    if r.is_system:
        raise PermissionError("system role cannot be deleted")
    in_use = db.execute(select(User).where(User.role_id == role_id)).first()
    if in_use:
        raise ValueError("role is assigned to users")
    db.delete(r); db.commit()
