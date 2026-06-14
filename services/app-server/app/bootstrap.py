from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.rbac import Role, Permission
from app.models.user import User
from app.auth import hash_password

PERMISSION_CATALOG = [
    ("dataset:read", "看数据集/版本"), ("dataset:write", "建数据集/传版本"),
    ("training:read", "看训练任务"), ("training:run", "发起训练"),
    ("model:read", "看模型版本"),
    ("eval:read", "看评估"), ("eval:run", "发起评估"),
    ("deploy:read", "看部署"), ("deploy:write", "部署/停止"),
    ("user:manage", "用户管理"), ("role:manage", "角色管理"),
    ("*", "通配"),
]
READS = ["dataset:read", "training:read", "model:read", "eval:read", "deploy:read"]
BUSINESS = READS + ["dataset:write", "training:run", "eval:run", "deploy:write"]
SYSTEM_ROLES = [
    ("superadmin", "超级管理员", "all", True, ["*"]),
    ("admin", "管理员", "all", False, BUSINESS),
    ("member", "成员", "own", False, BUSINESS),
    ("viewer", "只读", "own", False, READS),
]

def seed(db: Session) -> None:
    by_code = {}
    for code, desc in PERMISSION_CATALOG:
        p = db.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
        if not p:
            p = Permission(code=code, description=desc); db.add(p)
        by_code[code] = p
    db.flush()
    for name, desc, scope, is_sys, codes in SYSTEM_ROLES:
        r = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
        if not r:
            r = Role(name=name, description=desc, data_scope=scope, is_system=is_sys)
            db.add(r); db.flush()
        r.is_builtin = True   # all seeded roles are built-in (not deletable)
        r.permissions = [by_code[c] for c in codes]
    db.flush()
    superadmin = db.execute(select(Role).where(Role.name == "superadmin")).scalar_one()
    has_admin = db.execute(select(User).where(User.role_id == superadmin.id)).first()
    if not has_admin:
        db.add(User(name="admin", email=settings.seed_admin_email,
                    password_hash=hash_password(settings.seed_admin_password),
                    role_id=superadmin.id, is_active=True))
    db.commit()

def run() -> None:
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()

if __name__ == "__main__":
    run()
