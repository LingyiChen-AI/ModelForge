from modelforge_common.enums import TaskType, JobStatus, DatasetKind
from modelforge_common.task_names import TRAIN_TASK, EVAL_TASK

def test_task_type_values():
    assert TaskType.CLASSIFICATION.value == "classification"
    assert set(TaskType) >= {TaskType.CLASSIFICATION, TaskType.NER,
                             TaskType.PAIR, TaskType.EMBEDDING}

def test_job_status_terminal():
    assert JobStatus.SUCCEEDED.is_terminal()
    assert not JobStatus.RUNNING.is_terminal()

def test_task_names():
    assert TRAIN_TASK == "modelforge.train"
    assert EVAL_TASK == "modelforge.eval"
