from worker.recipes.base import Recipe
from worker.recipes.classification import ClassificationRecipe

def get_recipe(task_type: str) -> Recipe:
    if task_type == "classification":
        return ClassificationRecipe()
    raise NotImplementedError(f"recipe for {task_type} not implemented yet")
