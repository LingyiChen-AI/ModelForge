from server.predictors.classification import ClassificationPredictor
from server.predictors.ner import NERPredictor
from server.predictors.pair import PairPredictor
from server.predictors.embedding import EmbeddingPredictor
def build_predictor(task_type: str, model_dir: str):
    m = {"classification": ClassificationPredictor, "ner": NERPredictor,
         "pair": PairPredictor, "embedding": EmbeddingPredictor}
    if task_type not in m:
        raise NotImplementedError(f"predictor for {task_type} not implemented")
    return m[task_type](model_dir)
