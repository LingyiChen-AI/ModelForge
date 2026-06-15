"""Re-run a freshly trained model over the badcases it was trained on, to judge which
ones it now predicts correctly. `judge` is the pure comparison (unit-tested); `_predict`
loads the model exactly like the evaluators do; `score` ties them together."""
import json
import os
import numpy as np


def judge(task_type: str, prediction, annotation: dict) -> bool:
    """True if `prediction` matches the human annotation (the correct answer)."""
    annotation = annotation or {}
    if task_type in ("classification", "pair"):
        return str(prediction) == str(annotation.get("label"))
    if task_type == "ner":
        return list(prediction) == list(annotation.get("tags") or [])
    if task_type == "embedding":
        return prediction in (annotation.get("pos") or [])
    return False


def _predict_classification(model_dir, inputs):
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    with open(os.path.join(model_dir, "label_map.json")) as f:
        label2id = json.load(f)
    id2label = {i: lbl for lbl, i in label2id.items()}
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir); model.eval()
    texts = [str(x.get("text", "")) for x in inputs]
    preds = []
    for i in range(0, len(texts), 32):
        enc = tok(texts[i:i+32], truncation=True, padding=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = model(**enc).logits.cpu().numpy()
        preds.extend(id2label[int(j)] for j in np.argmax(logits, axis=-1))
    return preds


def _predict_pair(model_dir, inputs):
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir); model.eval()
    a = [str(x.get("text_a", "")) for x in inputs]
    b = [str(x.get("text_b", "")) for x in inputs]
    preds = []
    for i in range(0, len(a), 32):
        enc = tok(a[i:i+32], b[i:i+32], truncation=True, padding=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logit = model(**enc).logits.reshape(-1).cpu().numpy()
        sim = 1.0 / (1.0 + np.exp(-logit))   # same sigmoid as serving/eval
        preds.extend("1" if s >= 0.5 else "0" for s in sim)
    return preds


def _predict_ner(model_dir, inputs):
    from transformers import AutoTokenizer, AutoModelForTokenClassification
    import torch
    with open(os.path.join(model_dir, "tag_map.json")) as f:
        tag2id = json.load(f)
    id2tag = {i: t for t, i in tag2id.items()}
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForTokenClassification.from_pretrained(model_dir); model.eval()
    preds = []
    for x in inputs:
        tokens = [str(t) for t in (x.get("tokens") or [])]
        enc = tok([tokens], is_split_into_words=True, truncation=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = model(**enc).logits[0].cpu().numpy()
        p = np.argmax(logits, axis=-1)
        word_ids = enc.word_ids(batch_index=0)
        prev, seq = None, []
        for idx, wid in enumerate(word_ids):
            if wid is not None and wid != prev:
                seq.append(id2tag[int(p[idx])])
            prev = wid
        preds.append(seq)
    return preds


def _predict_embedding(model_dir, inputs):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_dir)
    preds = []
    for x in inputs:
        cands = list(x.get("candidates") or [])
        if not cands:
            preds.append(None); continue
        qe = model.encode([str(x.get("query", ""))], normalize_embeddings=True)
        ce = model.encode(cands, normalize_embeddings=True)
        sims = (qe @ ce.T)[0]
        preds.append(cands[int(np.argmax(sims))])
    return preds


_PREDICTORS = {
    "classification": _predict_classification,
    "pair": _predict_pair,
    "ner": _predict_ner,
    "embedding": _predict_embedding,
}


def score(task_type: str, model_dir: str, rows: list[dict]) -> list[bool]:
    """rows = [{"input": {...}, "annotation": {...}}]; returns per-row fixed booleans."""
    if not rows:
        return []
    predictor = _PREDICTORS.get(task_type)
    if predictor is None:
        return [False] * len(rows)
    preds = predictor(model_dir, [r["input"] for r in rows])
    return [judge(task_type, p, r["annotation"]) for p, r in zip(preds, rows)]
