from enum import Enum

class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    NER = "ner"
    PAIR = "pair"
    EMBEDDING = "embedding"

class DatasetKind(str, Enum):
    TRAIN = "train"      # 训练集 — model training
    EVAL = "eval"        # 评估集 — validation during training
    TEST = "test"        # 测试集 — model testing (model-test page)
    PROMPT = "prompt"    # Prompt 测试集 — 列即参数,供 Prompt 评测

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        return self in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
