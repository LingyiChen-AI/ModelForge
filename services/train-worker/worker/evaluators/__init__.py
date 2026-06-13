from worker.evaluators.base import Evaluator
from worker.evaluators.classification import ClassificationEvaluator

def get_evaluator(task_type: str) -> Evaluator:
    if task_type == "classification":
        return ClassificationEvaluator()
    raise NotImplementedError(f"evaluator for {task_type} not implemented yet")
