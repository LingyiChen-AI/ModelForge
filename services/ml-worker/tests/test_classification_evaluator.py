import pandas as pd, pytest
from worker.evaluators import get_evaluator
from worker.evaluators.classification import ClassificationEvaluator

def test_get_evaluator_classification():
    assert isinstance(get_evaluator("classification"), ClassificationEvaluator)

@pytest.mark.slow
def test_classification_evaluate_returns_metrics(tmp_path):
    from worker.recipes.classification import ClassificationRecipe
    train_df = pd.DataFrame({"text": ["good","bad","great","awful"]*4,
                             "label": ["pos","neg","pos","neg"]*4})
    ClassificationRecipe().train(df=train_df, base_model="prajjwal1/bert-tiny",
        hyperparams={"epochs": 1, "batch_size": 4, "max_length": 16},
        output_dir=str(tmp_path))
    eval_df = pd.DataFrame({"text": ["good","bad"], "label": ["pos","neg"]})
    metrics = ClassificationEvaluator().evaluate(model_dir=str(tmp_path), df=eval_df)
    assert "accuracy" in metrics and "f1" in metrics
    assert 0.0 <= metrics["accuracy"] <= 1.0
