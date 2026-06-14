from fastapi.testclient import TestClient
from tests.conftest import auth_headers

def _admin(db):
    from app.bootstrap import seed
    from sqlalchemy import select
    from app.models.user import User
    from app.models.rbac import Role
    seed(db)
    sa = db.execute(select(Role).where(Role.name=="superadmin")).scalar_one()
    return db.execute(select(User).where(User.role_id==sa.id)).scalar_one().id, sa.id

def test_role_crud(session_factory):
    S = session_factory; db = S()
    admin_id, sa_id = _admin(db); db.close()
    from app.main import app
    c = TestClient(app)
    H = auth_headers(admin_id)
    assert {p["code"] for p in c.get("/permissions", headers=H).json()} >= {"dataset:read","*"}
    r = c.post("/roles", json={"name":"labeler","data_scope":"own",
        "permission_codes":["dataset:read","dataset:write"]}, headers=H)
    assert r.status_code == 201 and set(r.json()["permissions"]) == {"dataset:read","dataset:write"}
    rid = r.json()["id"]
    r = c.patch(f"/roles/{rid}", json={"permission_codes":["dataset:read"]}, headers=H)
    assert set(r.json()["permissions"]) == {"dataset:read"}
    # rename + change data_scope on a custom role
    r = c.patch(f"/roles/{rid}", json={"name":"annotator","data_scope":"all"}, headers=H)
    assert r.status_code == 200 and r.json()["name"] == "annotator" and r.json()["data_scope"] == "all"
    # rename collision with an existing role → 409
    assert c.patch(f"/roles/{rid}", json={"name":"superadmin"}, headers=H).status_code == 409
    assert c.patch(f"/roles/{sa_id}", json={"description":"x"}, headers=H).status_code == 400
    assert c.delete(f"/roles/{sa_id}", headers=H).status_code == 400
    assert c.delete(f"/roles/{rid}", headers=H).status_code == 200

def test_builtin_roles_not_deletable(session_factory):
    from sqlalchemy import select
    from app.models.rbac import Role
    S = session_factory; db = S()
    admin_id, _ = _admin(db)
    # admin/member/viewer are built-in (not is_system) but must not be deletable
    builtin = {r.name: r for r in db.execute(select(Role)).scalars()}
    member_id = builtin["member"].id
    assert builtin["admin"].is_builtin and builtin["member"].is_builtin and builtin["viewer"].is_builtin
    db.close()
    from app.main import app
    c = TestClient(app)
    H = auth_headers(admin_id)
    assert c.delete(f"/roles/{member_id}", headers=H).status_code == 400
    # but a built-in (non-system) role is still editable
    assert c.patch(f"/roles/{member_id}", json={"description": "成员角色"}, headers=H).status_code == 200
    assert c.get("/roles", headers=H).json()[0]["is_builtin"] is True

def test_roles_requires_role_manage(session_factory):
    from tests.conftest import make_user
    S = session_factory; db = S()
    plain = make_user(db, codes=("dataset:read",), email="pp@x.com")
    pid = plain.id; db.close()
    from app.main import app
    c = TestClient(app)
    assert c.get("/roles", headers=auth_headers(pid)).status_code == 403
