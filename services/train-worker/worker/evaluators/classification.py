import json, os
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from worker.evaluators.base import Evaluator

class ClassificationEvaluator(Evaluator):
    def evaluate(self, model_dir: str, df) -> dict:
        with open(os.path.join(model_dir, "label_map.json")) as f:
            label2id = json.load(f)
        tok = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        model.eval()
        texts = df["text"].tolist()
        enc = tok(texts, truncation=True, padding=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = model(**enc).logits.cpu().numpy()
        pred = np.argmax(logits, axis=-1)
        y = df["label"].map(label2id).to_numpy()
        p, r, f1, _ = precision_recall_fscore_support(y, pred, average="macro", zero_division=0)
        return {"accuracy": float(accuracy_score(y, pred)),
                "precision": float(p), "recall": float(r), "f1": float(f1),
                "n_samples": int(len(df))}
