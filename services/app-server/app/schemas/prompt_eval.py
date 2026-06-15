from datetime import datetime
from pydantic import BaseModel


class PromptEvalCreate(BaseModel):
    eval_type: str
    name: str
    prompt_version_ids: list[int] = []
    model_ids: list[int] = []
    dataset_version_ids: list[int] = []


class ArmOut(BaseModel):
    id: int
    arm_index: int
    prompt_version_id: int
    model_id: int
    label: str

    class Config:
        from_attributes = True


class PromptEvalOut(BaseModel):
    id: int
    name: str
    eval_type: str
    status: str
    progress: float
    prompt_version_ids: list[int] = []
    model_ids: list[int] = []
    dataset_version_ids: list[int] = []
    compare_to_version_id: int | None = None
    created_by_name: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class PromptEvalDetailOut(PromptEvalOut):
    arms: list[ArmOut] = []


class OutputOut(BaseModel):
    id: int
    arm_id: int
    output_text: str
    status: str
    error: str | None = None
    latency_ms: int

    class Config:
        from_attributes = True


class ItemOut(BaseModel):
    id: int
    item_index: int
    dataset_version_id: int
    row_index: int
    inputs: dict
    outputs: list[OutputOut] = []
    winner_arm_id: int | None = None
    all_bad: bool = False
    is_good: bool | None = None
    annotated_by_name: str | None = None
    evaluated_at: datetime | None = None
    ai_winner_arm_id: int | None = None
    ai_all_bad: bool = False
    ai_is_good: bool | None = None
    ai_model_id: int | None = None
    ai_reasoning: str | None = None
    ai_evaluated_at: datetime | None = None

    class Config:
        from_attributes = True


class VerdictIn(BaseModel):
    winner_arm_id: int | None = None
    all_bad: bool = False
    is_good: bool | None = None


class AiEvaluateIn(BaseModel):
    model_id: int
