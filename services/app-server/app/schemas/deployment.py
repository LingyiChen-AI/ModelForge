from pydantic import BaseModel

class DeploymentCreate(BaseModel):
    model_version_id: int
    config: dict = {}

class DeploymentOut(BaseModel):
    id: int
    model_version_id: int
    status: str
    endpoint: str | None
    error: str | None
    class Config:
        from_attributes = True
