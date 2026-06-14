"""Shared API key algorithm — used by app-server (issue + verify) and model-server
(verify). Pure stdlib so any service can import it without extra deps."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime

PREFIX = "mf_"


def generate_key() -> tuple[str, str]:
    """Return (plaintext, key_prefix). Plaintext is shown once; store only its hash."""
    plaintext = PREFIX + secrets.token_urlsafe(24)
    return plaintext, plaintext[:len(PREFIX) + 8]   # mf_ (3) + 8 display chars


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def key_authorized(scopes: list[str] | str | None,
                   revoked_at: datetime | str | None,
                   scope: str) -> bool:
    """Pure authorization check given a fetched key row's scopes + revoked_at.
    `scopes` may be a list (ORM/PG JSON) or a JSON string (raw sqlite TEXT)."""
    if revoked_at is not None:
        return False
    if isinstance(scopes, str):
        try:
            scopes = json.loads(scopes)
        except (ValueError, TypeError):
            scopes = []
    return scope in (scopes or [])
