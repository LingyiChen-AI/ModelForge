from pydantic import BaseModel


class AiEvalPromptOut(BaseModel):
    value: str
    is_custom: bool = False   # 用户是否有自定义值(决定「还原默认」是否可用)


class AiEvalPromptIn(BaseModel):
    value: str = ""
