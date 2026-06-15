from datetime import datetime
from pydantic import BaseModel


class PromptVersionOut(BaseModel):
    id: int
    version_no: int
    system_prompt: str
    user_prompt: str
    params: list[str] = []
    note: str = ""
    created_by_name: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class PromptOut(BaseModel):
    id: int
    name: str
    created_by_name: str | None = None
    created_at: datetime
    latest_version_no: int | None = None
    latest_params: list[str] = []

    class Config:
        from_attributes = True


class PromptDetailOut(PromptOut):
    versions: list[PromptVersionOut] = []


class PromptCreate(BaseModel):
    name: str
    system_prompt: str = ""
    user_prompt: str = ""
    note: str = ""


class PromptVersionCreate(BaseModel):
    system_prompt: str = ""
    user_prompt: str = ""
    note: str = ""


class PromptValidateIn(BaseModel):
    system_prompt: str = ""
    user_prompt: str = ""


class PromptValidateOut(BaseModel):
    params: list[str]
    errors: list[str]


class PromptDatasetCreate(BaseModel):
    name: str
