from fastapi.testclient import TestClient
from tests.conftest import auth_headers

def _seed(db):
    from app.bootstrap import seed
    from sqlalchemy import select
    from app.models.user import User
    from app.models.rbac import Role
    seed(db)
    superadmin = db.execute(select(Role).where(Role.name=="superadmin")).scalar_one()
    admin = db.execute(select(User).where(User.role_id==superadmin.id)).scalar_one()
    member_role = db.execute(select(Role).where(Role.name=="member")).scalar_one()
    return admin.id, member_role.id, superadmin.id

def test_user_management_flow(session_factory):
    S = session_factory; db = S()
    admin_id, member_role_id, superadmin_role_id = _seed(db); db.close()
    from app.main import app
    c = TestClient(app)
    H = auth_headers(admin_id)
    r = c.post("/users", json={"name":"u1","email":"u1@x.com","password":"pw",
                               "role_id": member_role_id}, headers=H)
    assert r.status_code == 201
    uid = r.json()["id"]
    assert len(c.get("/users", headers=H).json()) == 2
    assert c.patch(f"/users/{uid}", json={"is_active": False}, headers=H).status_code == 200
    login = c.post("/auth/login", json={"email":"u1@x.com","password":"pw"})
    assert login.status_code == 401  # u1 停用后登录失败
    r = c.patch(f"/users/{admin_id}", json={"is_active": False}, headers=H)
    assert r.status_code == 422  # 最后一个 superadmin 不可停用

def test_requires_user_manage(session_factory):
    from tests.conftest import make_user
    S = session_factory; db = S()
    plain = make_user(db, codes=("dataset:read",), email="p@x.com")
    pid = plain.id; db.close()
    from app.main import app
    c = TestClient(app)
    assert c.get("/users", headers=auth_headers(pid)).status_code == 403
