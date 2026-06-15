from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from modelforge_common.apikey import generate_key, hash_key, key_authorized  # shared algorithm
from app.models.api_key import ApiKey

# re-exported so callers/tests can do api_key_service.hash_key(...)
__all__ = ["hash_key", "create_key", "verify", "list_keys", "revoke"]


def create_key(db: Session, *, name: str, scopes: list[str],
               created_by: int | None) -> tuple[str, ApiKey]:
    """Returns (plaintext, ApiKey). Plaintext is also stored so it can be re-copied."""
    plaintext, prefix = generate_key()
    key = ApiKey(name=name, key_prefix=prefix, key_hash=hash_key(plaintext),
                 plaintext=plaintext, scopes=list(scopes), created_by=created_by)
    db.add(key); db.commit(); db.refresh(key)
    return plaintext, key


def verify(db: Session, plaintext: str, scope: str) -> ApiKey | None:
    if not plaintext:
        return None
    key = db.execute(select(ApiKey).where(ApiKey.key_hash == hash_key(plaintext))).scalar_one_or_none()
    if not key or not key_authorized(key.scopes, key.revoked_at, scope):
        return None
    key.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return key


def list_keys(db: Session) -> list[ApiKey]:
    return list(db.execute(select(ApiKey).order_by(ApiKey.id.desc())).scalars())


def revoke(db: Session, key_id: int) -> bool:
    key = db.get(ApiKey, key_id)
    if not key or key.revoked_at is not None:
        return False
    key.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return True
