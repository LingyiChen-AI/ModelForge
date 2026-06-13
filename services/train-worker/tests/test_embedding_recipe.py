import pandas as pd, pytest
from worker.recipes import get_recipe
from worker.recipes.embedding import EmbeddingRecipe
from worker.evaluators import get_evaluator
from worker.evaluators.embedding import EmbeddingEvaluator

def test_get_recipe_embedding():
    assert isinstance(get_recipe("embedding"), EmbeddingRecipe)

def test_get_evaluator_embedding():
    assert isinstance(get_evaluator("embedding"), EmbeddingEvaluator)

def test_mine_hard_negatives_basic():
    df = pd.DataFrame({"query": ["q1","q2"], "pos": [["p1"],["p2"]], "neg": [[],[]]})
    rows = EmbeddingRecipe()._prepare_examples(df, negatives_mode="provided")
    assert len(rows) >= 2

@pytest.mark.slow
def test_embedding_trains_and_evaluates(tmp_path):
    df = pd.DataFrame({
        "query": ["cat","dog","car","tree"] * 3,
        "pos": [["a small kitten"],["a puppy"],["a fast vehicle"],["a tall plant"]] * 3,
        "neg": [[],[],[],[]] * 3})
    res = EmbeddingRecipe().train(df=df, base_model="prajjwal1/bert-tiny",
        hyperparams={"epochs": 1, "batch_size": 4}, output_dir=str(tmp_path))
    assert res.artifact_dir == str(tmp_path)
    metrics = EmbeddingEvaluator().evaluate(model_dir=str(tmp_path), df=df)
    assert "recall@1" in metrics and 0.0 <= metrics["recall@1"] <= 1.0
