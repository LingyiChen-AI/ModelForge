import numpy as np
from sentence_transformers import SentenceTransformer
from worker.evaluators.base import Evaluator

class EmbeddingEvaluator(Evaluator):
    def evaluate(self, model_dir: str, df, on_progress=None, ks=(1, 3, 5)) -> dict:
        model = SentenceTransformer(model_dir)
        corpus, gold = [], []
        for _, r in df.reset_index(drop=True).iterrows():
            gold.append(len(corpus))
            corpus.extend(r["pos"])
        queries = df["query"].tolist()
        if on_progress: on_progress(0.2)
        qe = model.encode(queries, normalize_embeddings=True)
        if on_progress: on_progress(0.6)
        ce = model.encode(corpus, normalize_embeddings=True)
        if on_progress: on_progress(0.95)
        sims = qe @ ce.T
        ranks = np.argsort(-sims, axis=1)
        out = {}
        for k in ks:
            hits = sum(1 for i, g in enumerate(gold) if g in ranks[i, :k].tolist())
            out[f"recall@{k}"] = float(hits / len(gold))
        out["n_samples"] = int(len(df))
        # 逐条预测(检索任务:查询 + 标注正例 + 命中的 Top1 文本 + Top1 是否命中)。
        kmax = max(ks)
        predictions = []
        for i, g in enumerate(gold):
            top1 = int(ranks[i, 0])
            predictions.append({"row": i, "query": queries[i],
                                "expected": corpus[g], "predicted": corpus[top1],
                                "correct": bool(top1 == g),
                                f"命中Top{kmax}": bool(g in ranks[i, :kmax].tolist())})
        out["predictions"] = predictions
        return out
