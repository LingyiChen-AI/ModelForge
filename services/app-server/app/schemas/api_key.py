from datetime import datetime
from pydantic import BaseModel

VALID_SCOPES = {"inference", "badcase:report"}

class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = []

class ApiKeyOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    plaintext: str | None = None   # full key for re-copy (null for pre-existing keys)
    scopes: list[str]
    created_by_name: str | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    class Config: from_attributes = True

class ApiKeyCreated(ApiKeyOut):
    plaintext: str   # one-time secret
