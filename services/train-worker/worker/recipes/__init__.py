from worker.recipes.base import Recipe
from worker.recipes.classification import ClassificationRecipe
from worker.recipes.ner import NERRecipe
from worker.recipes.pair import PairRecipe
from worker.recipes.embedding import EmbeddingRecipe

def get_recipe(task_type: str) -> Recipe:
    if task_type == "classification":
        return ClassificationRecipe()
    if task_type == "ner":
        return NERRecipe()
    if task_type == "pair":
        return PairRecipe()
    if task_type == "embedding":
        return EmbeddingRecipe()
    raise NotImplementedError(f"recipe for {task_type} not implemented yet")
