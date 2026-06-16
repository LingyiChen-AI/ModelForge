import numpy as np
from scipy.stats import spearmanr, pearsonr
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from worker.evaluators.base import Evaluator, batched_logits
from worker.recipes.pair import _targets

class PairEvaluator(Evaluator):
    def evaluate(self, model_dir: str, df, on_progress=None) -> dict:
        tok = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForSequenceClassification.from_pretrained(model_dir); model.eval()
        a, b = df["text_a"].tolist(), df["text_b"].tolist()
        def encode(i, j): return tok(a[i:j], b[i:j], truncation=True, padding=True, max_length=256, return_tensors="pt")
        preds = batched_logits(model, encode, len(a), on_progress).reshape(-1)
        preds = 1.0 / (1.0 + np.exp(-preds))   # (0,1) similarity, consistent with serving
        y = np.array(_targets(df), dtype=float)
        sp = spearmanr(preds, y).correlation if len(set(y.tolist())) > 1 else 0.0
        pe = pearsonr(preds, y)[0] if len(set(y.tolist())) > 1 else 0.0
        return {"spearman": float(sp if sp == sp else 0.0),
                "pearson": float(pe if pe == pe else 0.0),
                "mse": float(np.mean((preds - y) ** 2)), "n_samples": int(len(df))}
