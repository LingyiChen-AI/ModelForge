import json, os
import numpy as np, torch
from transformers import AutoTokenizer, AutoModelForTokenClassification
from server.predictors.base import Predictor
class NERPredictor(Predictor):
    def __init__(self, model_dir):
        with open(os.path.join(model_dir, "tag_map.json")) as f:
            self.id2tag = {v: k for k, v in json.load(f).items()}
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForTokenClassification.from_pretrained(model_dir); self.model.eval()
    def predict(self, token_lists):
        results = []
        for tokens in token_lists:
            enc = self.tok([tokens], is_split_into_words=True, truncation=True,
                           max_length=256, return_tensors="pt")
            with torch.no_grad():
                logits = self.model(**enc).logits[0].cpu().numpy()
            p = np.argmax(logits, axis=-1)
            word_ids = enc.word_ids(batch_index=0)
            prev, tags = None, []
            for idx, wid in enumerate(word_ids):
                if wid is not None and wid != prev:
                    tags.append(self.id2tag[int(p[idx])])
                prev = wid
            results.append(tags)
        return results
