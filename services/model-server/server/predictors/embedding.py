from sentence_transformers import SentenceTransformer
from server.predictors.base import Predictor
class EmbeddingPredictor(Predictor):
    def __init__(self, model_dir):
        self.model = SentenceTransformer(model_dir)
    def embed(self, texts):
        return [[float(x) for x in v] for v in self.model.encode(texts, normalize_embeddings=True)]
