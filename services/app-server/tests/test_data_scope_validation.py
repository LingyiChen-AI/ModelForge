from fastapi.testclient import TestClient
from tests.conftest import auth_headers

def _admin(db):
    from app.bootstrap import seed
    from sqlalchemy import select
    from app.models.user import User
    from app.models.rbac import Role
    seed(db)
    sa = db.execute(select(Role).where(Role.name=="superadmin")).scalar_one()
    return db.execute(select(User).where(User.role_id==sa.id)).scalar_one().id

def test_invalid_data_scope_rejected(session_factory):
    S = session_factory; db = S()
    admin_id = _admin(db); db.close()
    from app.main import app
    c = TestClient(app)
    H = auth_headers(admin_id)
    # 非法 data_scope → 422
    r = c.post("/roles", json={"name":"bad","data_scope":"team","permission_codes":[]}, headers=H)
    assert r.status_code == 422
    # 合法 own → 201
    r = c.post("/roles", json={"name":"good","data_scope":"own","permission_codes":[]}, headers=H)
    assert r.status_code == 201
