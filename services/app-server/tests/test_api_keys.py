def test_api_key_model_roundtrip(session_factory):
    from app.models.api_key import ApiKey
    db = session_factory()
    k = ApiKey(name="svc", key_prefix="mf_abc123", key_hash="deadbeef",
               scopes=["badcase:report", "inference"])
    db.add(k); db.commit(); db.refresh(k)
    assert k.id and k.revoked_at is None and "inference" in k.scopes
