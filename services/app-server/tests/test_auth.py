import pytest
from app.auth import hash_password, verify_password, create_access_token, decode_token

def test_password_roundtrip():
    h = hash_password("secret")
    assert h != "secret"
    assert verify_password("secret", h)
    assert not verify_password("wrong", h)

def test_jwt_roundtrip():
    tok = create_access_token(42)
    assert decode_token(tok)["sub"] == "42"

def test_jwt_invalid():
    with pytest.raises(Exception):
        decode_token("not-a-token")
