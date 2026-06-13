from enum import Enum

class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    NER = "ner"
    PAIR = "pair"
    EMBEDDING = "embedding"

class DatasetKind(str, Enum):
    TRAIN = "train"
    EVAL = "eval"

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        return self in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
