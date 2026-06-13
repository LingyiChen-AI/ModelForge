from worker.evaluators.base import Evaluator
from worker.evaluators.classification import ClassificationEvaluator
from worker.evaluators.ner import NEREvaluator
from worker.evaluators.pair import PairEvaluator
from worker.evaluators.embedding import EmbeddingEvaluator

def get_evaluator(task_type: str) -> Evaluator:
    if task_type == "classification":
        return ClassificationEvaluator()
    if task_type == "ner":
        return NEREvaluator()
    if task_type == "pair":
        return PairEvaluator()
    if task_type == "embedding":
        return EmbeddingEvaluator()
    raise NotImplementedError(f"evaluator for {task_type} not implemented yet")
