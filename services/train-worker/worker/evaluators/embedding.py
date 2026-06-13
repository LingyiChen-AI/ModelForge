import numpy as np
from sentence_transformers import SentenceTransformer
from worker.evaluators.base import Evaluator

class EmbeddingEvaluator(Evaluator):
    def evaluate(self, model_dir: str, df, ks=(1, 3, 5)) -> dict:
        model = SentenceTransformer(model_dir)
        corpus, gold = [], []
        for _, r in df.reset_index(drop=True).iterrows():
            gold.append(len(corpus))
            corpus.extend(r["pos"])
        queries = df["query"].tolist()
        qe = model.encode(queries, normalize_embeddings=True)
        ce = model.encode(corpus, normalize_embeddings=True)
        sims = qe @ ce.T
        ranks = np.argsort(-sims, axis=1)
        out = {}
        for k in ks:
            hits = sum(1 for i, g in enumerate(gold) if g in ranks[i, :k].tolist())
            out[f"recall@{k}"] = float(hits / len(gold))
        out["n_samples"] = int(len(df))
        return out
