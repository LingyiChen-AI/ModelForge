import json, os
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification
from seqeval.metrics import accuracy_score, f1_score, precision_score, recall_score
from worker.evaluators.base import Evaluator

class NEREvaluator(Evaluator):
    def evaluate(self, model_dir: str, df, on_progress=None) -> dict:
        with open(os.path.join(model_dir, "tag_map.json")) as f:
            tag2id = json.load(f)
        id2tag = {i: t for t, i in tag2id.items()}
        tok = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForTokenClassification.from_pretrained(model_dir); model.eval()
        true, pred = [], []
        n = len(df)
        for _i, (tokens, tags) in enumerate(zip(df["tokens"], df["tags"])):
            # parquet/np may hand back ndarray rows; the fast tokenizer only accepts plain list[str]
            tokens = [str(t) for t in tokens]
            tags = [str(t) for t in tags]
            enc = tok([tokens], is_split_into_words=True, truncation=True,
                      max_length=256, return_tensors="pt")
            with torch.no_grad():
                logits = model(**enc).logits[0].cpu().numpy()
            p = np.argmax(logits, axis=-1)
            word_ids = enc.word_ids(batch_index=0)
            prev, t_seq, p_seq = None, [], []
            for idx, wid in enumerate(word_ids):
                if wid is not None and wid != prev:
                    t_seq.append(tags[wid]); p_seq.append(id2tag[int(p[idx])])
                prev = wid
            true.append(t_seq); pred.append(p_seq)
            if on_progress and (_i % 5 == 0 or _i == n - 1):
                try: on_progress((_i + 1) / max(1, n))
                except Exception: pass
        return {"accuracy": float(accuracy_score(true, pred)),
                "precision": float(precision_score(true, pred)),
                "recall": float(recall_score(true, pred)),
                "f1": float(f1_score(true, pred)), "n_samples": int(len(df))}
