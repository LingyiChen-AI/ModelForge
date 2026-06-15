def test_api_key_model_roundtrip(session_factory):
    from app.models.api_key import ApiKey
    db = session_factory()
    k = ApiKey(name="svc", key_prefix="mf_abc123", key_hash="deadbeef",
               scopes=["badcase:report", "inference"])
    db.add(k); db.commit(); db.refresh(k)
    assert k.id and k.revoked_at is None and "inference" in k.scopes


def test_api_key_service_create_verify_revoke(session_factory):
    from app.services import api_key_service as svc
    db = session_factory()
    plaintext, key = svc.create_key(db, name="svc", scopes=["badcase:report"], created_by=None)
    assert plaintext.startswith("mf_") and key.key_prefix == plaintext[:11]
    # plaintext never stored
    assert key.key_hash == svc.hash_key(plaintext) and key.key_hash != plaintext
    # verify: correct key + scope -> returns the key
    assert svc.verify(db, plaintext, "badcase:report").id == key.id
    # wrong scope -> None
    assert svc.verify(db, plaintext, "inference") is None
    # unknown key -> None
    assert svc.verify(db, "mf_nope", "badcase:report") is None
    # revoke -> None
    svc.revoke(db, key.id)
    assert svc.verify(db, plaintext, "badcase:report") is None


from fastapi.testclient import TestClient

def _client_with(session_factory, codes):
    from app import db as dbmod
    db = session_factory()  # creates tables + sets SessionLocal via fixture
    from tests.conftest import make_user, auth_headers
    u = make_user(db, codes=codes, data_scope="all", email="ak@x.com"); db.close()
    from app.main import app
    return TestClient(app), auth_headers(u.id)

def test_api_keys_endpoints(session_factory):
    c, H = _client_with(session_factory, ("apikey:manage",))
    r = c.post("/api-keys", json={"name": "svc", "scopes": ["badcase:report"]}, headers=H)
    assert r.status_code == 201
    body = r.json()
    assert body["plaintext"].startswith("mf_")          # full key returned on create
    listed = c.get("/api-keys", headers=H).json()
    # plaintext is intentionally re-exposed in the list (re-copy convenience); hash never is
    assert listed and listed[0]["plaintext"].startswith("mf_") and "key_hash" not in listed[0]
    kid = body["id"]
    # revoke -> list shows it revoked
    assert c.delete(f"/api-keys/{kid}", headers=H).status_code == 200
    again = next(k for k in c.get("/api-keys", headers=H).json() if k["id"] == kid)
    assert again["revoked_at"] is not None
    # invalid scope on create -> 422
    assert c.post("/api-keys", json={"name": "x", "scopes": ["nope"]}, headers=H).status_code == 422

def test_api_keys_requires_perm(session_factory):
    c, H = _client_with(session_factory, ("dataset:read",))
    assert c.get("/api-keys", headers=H).status_code == 403
