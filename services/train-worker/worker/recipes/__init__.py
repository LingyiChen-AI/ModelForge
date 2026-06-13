from worker.recipes.base import Recipe
from worker.recipes.classification import ClassificationRecipe
from worker.recipes.ner import NERRecipe

def get_recipe(task_type: str) -> Recipe:
    if task_type == "classification":
        return ClassificationRecipe()
    if task_type == "ner":
        return NERRecipe()
    raise NotImplementedError(f"recipe for {task_type} not implemented yet")
