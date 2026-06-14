import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from tests.conftest import make_user, auth_headers


def test_has_permission_and_scope(session_factory):
    from app.authz import has_permission, effective_scope
    S = session_factory; db = S()
    admin = make_user(db, codes=("*",), data_scope="all", email="ad@x.com")
    member = make_user(db, codes=("dataset:read",), data_scope="own", email="mb@x.com")
    assert has_permission(admin, "anything:at:all")  # 通配
    assert has_permission(member, "dataset:read")
    assert not has_permission(member, "dataset:write")
    assert effective_scope(admin) == "all"   # 通配视为 all
    assert effective_scope(member) == "own"


def test_require_dependency(session_factory):
    from app.authz import require
    S = session_factory; db = S()
    member = make_user(db, codes=("dataset:read",), email="m@x.com", data_scope="own")
    mid = member.id; db.close()
    app = FastAPI()
    @app.get("/x")
    def x(u=Depends(require("dataset:write"))):
        return {"ok": True}
    c = TestClient(app)
    assert c.get("/x").status_code == 401                       # 无 token
    assert c.get("/x", headers=auth_headers(mid)).status_code == 403  # 有 token 无权限
