import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from modelforge_common.apikey import hash_key
import server.api_auth as auth

def _engine_with_key(tmp_path, plaintext, scopes='["inference"]', revoked=None):
    eng = create_engine(f"sqlite:///{tmp_path}/k.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE IF NOT EXISTS api_keys "
                       "(key_hash TEXT, scopes TEXT, revoked_at TIMESTAMP)"))
        c.execute(text("INSERT INTO api_keys (key_hash, scopes, revoked_at) "
                       "VALUES (:h, :s, :r)"),
                  {"h": hash_key(plaintext), "s": scopes, "r": revoked})
    return eng

def test_require_api_key(monkeypatch, tmp_path):
    eng = _engine_with_key(tmp_path, "good")
    monkeypatch.setattr(auth, "_get_engine", lambda: eng)
    dep = auth.require_api_key("inference")
    assert dep(x_api_key="good") is None                 # valid
    with pytest.raises(HTTPException) as e:
        dep(x_api_key="bad")                              # unknown key
    assert e.value.status_code == 401
    with pytest.raises(HTTPException) as e:
        dep(x_api_key=None)                               # missing key
    assert e.value.status_code == 401
    with pytest.raises(HTTPException) as e:
        auth.require_api_key("badcase:report")(x_api_key="good")  # wrong scope
    assert e.value.status_code == 401

def test_require_api_key_revoked(monkeypatch, tmp_path):
    eng = _engine_with_key(tmp_path, "good", revoked="2026-01-01 00:00:00")
    monkeypatch.setattr(auth, "_get_engine", lambda: eng)
    with pytest.raises(HTTPException) as e:
        auth.require_api_key("inference")(x_api_key="good")
    assert e.value.status_code == 401

def test_require_api_key_db_unavailable_fails_closed(monkeypatch):
    def boom():
        raise Exception("db down")
    monkeypatch.setattr(auth, "_get_engine", boom)
    with pytest.raises(HTTPException) as e:
        auth.require_api_key("inference")(x_api_key="somekey")
    assert e.value.status_code == 503
