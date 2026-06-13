import pandas as pd, pytest
from worker.recipes import get_recipe
from worker.recipes.classification import ClassificationRecipe

def test_get_recipe_classification():
    assert isinstance(get_recipe("classification"), ClassificationRecipe)

@pytest.mark.slow
def test_classification_trains_and_returns_metrics(tmp_path):
    df = pd.DataFrame({"text": ["good", "bad", "great", "awful"] * 4,
                       "label": ["pos", "neg", "pos", "neg"] * 4})
    recipe = ClassificationRecipe()
    result = recipe.train(
        df=df, base_model="prajjwal1/bert-tiny",
        hyperparams={"epochs": 1, "batch_size": 4, "max_length": 16},
        output_dir=str(tmp_path))
    assert "accuracy" in result.metrics
    assert result.label_names == ["neg", "pos"]
    assert (tmp_path / "label_map.json").exists()
