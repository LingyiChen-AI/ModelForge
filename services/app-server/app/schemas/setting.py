from pydantic import BaseModel


class AiEvalPromptOut(BaseModel):
    value: str


class AiEvalPromptIn(BaseModel):
    value: str = ""
