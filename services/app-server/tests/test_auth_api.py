from fastapi.testclient import TestClient
from tests.conftest import make_user, auth_headers

def test_login_and_me(session_factory):
    S = session_factory
    db = S()
    from app.auth import hash_password
    u = make_user(db, codes=("dataset:read", "dataset:write"), data_scope="own",
                  email="a@x.com")
    u.password_hash = hash_password("pw"); db.add(u); db.commit()
    uid = u.id; db.close()

    from app.main import app
    c = TestClient(app)
    r = c.post("/auth/login", json={"email": "a@x.com", "password": "pw"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert set(body["user"]["permissions"]) == {"dataset:read", "dataset:write"}
    assert body["user"]["data_scope"] == "own"

    r = c.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert r.status_code == 200 and r.json()["email"] == "a@x.com"

    assert c.post("/auth/login", json={"email": "a@x.com", "password": "bad"}).status_code == 401
    assert c.get("/auth/me").status_code == 401  # 无 token
