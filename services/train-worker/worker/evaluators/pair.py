import numpy as np
import torch
from scipy.stats import spearmanr, pearsonr
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from worker.evaluators.base import Evaluator
from worker.recipes.pair import _targets

class PairEvaluator(Evaluator):
    def evaluate(self, model_dir: str, df) -> dict:
        tok = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForSequenceClassification.from_pretrained(model_dir); model.eval()
        enc = tok(df["text_a"].tolist(), df["text_b"].tolist(),
                  truncation=True, padding=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            preds = model(**enc).logits.reshape(-1).cpu().numpy()
        y = np.array(_targets(df), dtype=float)
        sp = spearmanr(preds, y).correlation if len(set(y.tolist())) > 1 else 0.0
        pe = pearsonr(preds, y)[0] if len(set(y.tolist())) > 1 else 0.0
        return {"spearman": float(sp if sp == sp else 0.0),
                "pearson": float(pe if pe == pe else 0.0),
                "mse": float(np.mean((preds - y) ** 2)), "n_samples": int(len(df))}
