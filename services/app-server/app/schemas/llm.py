from datetime import datetime
from pydantic import BaseModel


class LlmModelOut(BaseModel):
    id: int
    model_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ProviderCreate(BaseModel):
    name: str
    base_url: str
    api_key: str
    model_ids: list[str] = []


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    enabled: bool | None = None
    api_key: str | None = None   # 留空/None = 不改


class ProviderOut(BaseModel):
    id: int
    name: str
    base_url: str
    masked_key: str              # 读 LlmProvider.masked_key 属性;完整 key 不出现
    enabled: bool
    created_by_name: str | None = None
    created_at: datetime
    models: list[LlmModelOut] = []

    class Config:
        from_attributes = True


class ModelAddIn(BaseModel):
    model_id: str


class TestResult(BaseModel):
    ok: bool
    reply: str | None = None
    latency_ms: int
    error: str | None = None
