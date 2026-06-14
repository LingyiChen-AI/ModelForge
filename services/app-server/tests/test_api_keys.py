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
