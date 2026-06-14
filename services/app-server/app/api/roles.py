from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.authz import require
from app.models.user import User
from app.models.rbac import Role, Permission
from app.schemas.rbac import RoleCreate, RoleUpdate, RoleOut, PermissionOut
from app.services import role_service

router = APIRouter(tags=["roles"])

def _role_out(r: Role) -> RoleOut:
    return RoleOut(id=r.id, name=r.name, description=r.description,
                   data_scope=r.data_scope, is_system=r.is_system, is_builtin=r.is_builtin,
                   permissions=sorted(p.code for p in r.permissions),
                   created_at=r.created_at)

@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(_: User = Depends(require("role:manage")), db: Session = Depends(get_db)):
    return db.execute(select(Permission).order_by(Permission.code)).scalars().all()

@router.get("/roles", response_model=list[RoleOut])
def list_roles(_: User = Depends(require("role:manage")), db: Session = Depends(get_db)):
    return [_role_out(r) for r in db.execute(select(Role).order_by(Role.id)).scalars()]

@router.post("/roles", response_model=RoleOut, status_code=201)
def create(body: RoleCreate, _: User = Depends(require("role:manage")),
           db: Session = Depends(get_db)):
    try:
        return _role_out(role_service.create_role(db, body))
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.patch("/roles/{role_id}", response_model=RoleOut)
def update(role_id: int, body: RoleUpdate, _: User = Depends(require("role:manage")),
           db: Session = Depends(get_db)):
    try:
        return _role_out(role_service.update_role(db, role_id, body))
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg else (409 if "exists" in msg else 422)
        raise HTTPException(code, msg)
    except PermissionError as e:
        raise HTTPException(400, str(e))

@router.delete("/roles/{role_id}")
def delete(role_id: int, _: User = Depends(require("role:manage")),
           db: Session = Depends(get_db)):
    try:
        role_service.delete_role(db, role_id); return {"deleted": True}
    except PermissionError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        msg = str(e)
        raise HTTPException(409 if "assigned" in msg else 404, msg)
