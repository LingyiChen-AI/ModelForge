from worker.evaluators.base import Evaluator
from worker.evaluators.classification import ClassificationEvaluator
from worker.evaluators.ner import NEREvaluator

def get_evaluator(task_type: str) -> Evaluator:
    if task_type == "classification":
        return ClassificationEvaluator()
    if task_type == "ner":
        return NEREvaluator()
    raise NotImplementedError(f"evaluator for {task_type} not implemented yet")
