import pandas as pd, pytest
from worker.recipes import get_recipe
from worker.recipes.ner import NERRecipe
from worker.evaluators import get_evaluator
from worker.evaluators.ner import NEREvaluator

def test_get_recipe_ner():
    assert isinstance(get_recipe("ner"), NERRecipe)

def test_get_evaluator_ner():
    assert isinstance(get_evaluator("ner"), NEREvaluator)

@pytest.mark.slow
def test_ner_trains_and_evaluates(tmp_path):
    toks = [["I","love","Beijing"],["Cats","are","cute"]] * 6
    tags = [["O","O","B-LOC"],["O","O","O"]] * 6
    df = pd.DataFrame({"tokens": toks, "tags": tags})
    res = NERRecipe().train(df=df, base_model="prajjwal1/bert-tiny",
        hyperparams={"epochs": 1, "batch_size": 4, "max_length": 16},
        output_dir=str(tmp_path))
    assert "f1" in res.metrics
    metrics = NEREvaluator().evaluate(model_dir=str(tmp_path), df=df)
    assert "f1" in metrics and 0.0 <= metrics["f1"] <= 1.0
