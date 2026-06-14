"""Test-session configuration.

moto's ``mock_aws`` only intercepts boto3 calls that target the real AWS S3
endpoints. The application's default ``s3_endpoint_url`` is the MinIO address
``http://localhost:9000`` (see ``app/config.py``), which moto treats as a
pass-through and does not mock — boto3 then tries to reach the real host and
fails with a 502. For the duration of the test session we clear the endpoint
override so boto3 uses the default AWS endpoint that moto intercepts. Production
behaviour is unchanged.
"""
from app.config import settings

settings.s3_endpoint_url = None


# --- RBAC 测试助手 ---
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def session_factory(tmp_path):
    from app.models import Base
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(eng)
    from app import db as dbmod
    dbmod.SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    return dbmod.SessionLocal

def make_user(db, *, codes=("*",), data_scope="all", email="u@x.com",
              name="u", active=True):
    from app.models.rbac import Role, Permission
    from app.models.user import User
    from sqlalchemy import select
    perms = []
    for c in codes:
        p = db.execute(select(Permission).where(Permission.code == c)).scalar_one_or_none()
        if p is None:
            p = Permission(code=c, description=c)
            db.add(p)
        perms.append(p)
    role = Role(name=f"role-{email}", data_scope=data_scope, permissions=perms)
    db.add(role); db.commit()
    u = User(name=name, email=email, role_id=role.id, is_active=active)
    db.add(u); db.commit(); db.refresh(u)
    return u

def auth_headers(user_id):
    from app.auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}
