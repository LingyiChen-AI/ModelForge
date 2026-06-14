from datetime import datetime
from typing import Literal
from pydantic import BaseModel

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role_id: int | None = None

class UserUpdate(BaseModel):
    role_id: int | None = None
    is_active: bool | None = None

class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role_id: int | None
    is_active: bool
    created_at: datetime
    class Config: from_attributes = True

class PasswordReset(BaseModel):
    password: str

class RoleCreate(BaseModel):
    name: str
    description: str = ""
    data_scope: Literal["all", "own"] = "own"
    permission_codes: list[str] = []

class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    data_scope: Literal["all", "own"] | None = None
    permission_codes: list[str] | None = None

class RoleOut(BaseModel):
    id: int
    name: str
    description: str
    data_scope: str
    is_system: bool
    is_builtin: bool
    permissions: list[str]
    created_at: datetime

class PermissionOut(BaseModel):
    code: str
    description: str
