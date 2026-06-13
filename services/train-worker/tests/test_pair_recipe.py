import pandas as pd, pytest
from worker.recipes import get_recipe
from worker.recipes.pair import PairRecipe
from worker.evaluators import get_evaluator
from worker.evaluators.pair import PairEvaluator

def test_get_recipe_pair():
    assert isinstance(get_recipe("pair"), PairRecipe)

def test_get_evaluator_pair():
    assert isinstance(get_evaluator("pair"), PairEvaluator)

@pytest.mark.slow
def test_pair_trains_and_evaluates(tmp_path):
    df = pd.DataFrame({
        "text_a": ["cat","hello","good day","bye"] * 4,
        "text_b": ["kitten","hi","nice day","leave"] * 4,
        "score": [1.0, 1.0, 1.0, 0.0] * 4})
    res = PairRecipe().train(df=df, base_model="prajjwal1/bert-tiny",
        hyperparams={"epochs": 1, "batch_size": 4, "max_length": 16}, output_dir=str(tmp_path))
    assert "mse" in res.metrics
    metrics = PairEvaluator().evaluate(model_dir=str(tmp_path), df=df)
    assert "spearman" in metrics
