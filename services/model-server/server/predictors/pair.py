import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from server.predictors.base import Predictor
class PairPredictor(Predictor):
    def __init__(self, model_dir):
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir); self.model.eval()
    def similarity(self, pairs):
        a = [p[0] for p in pairs]; b = [p[1] for p in pairs]
        enc = self.tok(a, b, truncation=True, padding=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = self.model(**enc).logits.reshape(-1).cpu().numpy()
        return [float(x) for x in logits]
