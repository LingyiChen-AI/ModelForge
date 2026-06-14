from pydantic import BaseModel

class LoginRequest(BaseModel):
    email: str
    password: str

class UserInfo(BaseModel):
    id: int
    name: str
    email: str
    role: str | None
    data_scope: str
    permissions: list[str]

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
