import pandas as pd, pytest
from server.predictors import build_predictor
from server.predictors.classification import ClassificationPredictor

def test_build_predictor_unknown():
    with pytest.raises(NotImplementedError):
        build_predictor("nope", "/tmp")

@pytest.mark.slow
def test_classification_predictor(tmp_path):
    import sys; sys.path.insert(0, "/Users/chenhao/codes/myself/ModelForge/services/ml-worker")
    from worker.recipes.classification import ClassificationRecipe
    df = pd.DataFrame({"text": ["good","bad","great","awful"]*4, "label": ["pos","neg","pos","neg"]*4})
    ClassificationRecipe().train(df=df, base_model="prajjwal1/bert-tiny",
        hyperparams={"epochs":1,"batch_size":4,"max_length":16}, output_dir=str(tmp_path))
    pred = build_predictor("classification", str(tmp_path))
    out = pred.predict(["good", "awful"])
    assert len(out) == 2 and "label" in out[0] and "score" in out[0]
