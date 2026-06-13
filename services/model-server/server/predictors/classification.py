import json, os
import numpy as np, torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from server.predictors.base import Predictor
class ClassificationPredictor(Predictor):
    def __init__(self, model_dir):
        with open(os.path.join(model_dir, "label_map.json")) as f:
            self.id2label = {v: k for k, v in json.load(f).items()}
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir); self.model.eval()
    def predict(self, texts):
        enc = self.tok(texts, truncation=True, padding=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = self.model(**enc).logits
        probs = torch.softmax(logits, dim=-1).cpu().numpy()
        out = []
        for row in probs:
            i = int(np.argmax(row))
            out.append({"label": self.id2label[i], "score": float(row[i])})
        return out
