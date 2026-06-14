from fastapi import Header, HTTPException
from sqlalchemy import create_engine, text
from modelforge_common.apikey import hash_key, key_authorized
from server.config import settings

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def require_api_key(scope: str):
    def dep(x_api_key: str | None = Header(default=None)):
        if not x_api_key:
            raise HTTPException(401, "missing api key")
        try:
            with _get_engine().connect() as c:
                row = c.execute(
                    text("SELECT scopes, revoked_at FROM api_keys WHERE key_hash = :h"),
                    {"h": hash_key(x_api_key)}).mappings().first()
        except Exception:
            raise HTTPException(503, "auth backend unavailable")  # fail-closed
        if not row or not key_authorized(row["scopes"], row["revoked_at"], scope):
            raise HTTPException(401, "invalid or unauthorized api key")
        return None
    return dep
