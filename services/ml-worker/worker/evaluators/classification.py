import json, os
import numpy as np
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from worker.evaluators.base import Evaluator, batched_logits

class ClassificationEvaluator(Evaluator):
    def evaluate(self, model_dir: str, df, on_progress=None) -> dict:
        with open(os.path.join(model_dir, "label_map.json")) as f:
            label2id = json.load(f)
        tok = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        model.eval()
        texts = df["text"].tolist()
        def encode(i, j): return tok(texts[i:j], truncation=True, padding=True, max_length=256, return_tensors="pt")
        logits = batched_logits(model, encode, len(texts), on_progress)
        pred = np.argmax(logits, axis=-1)
        # map test labels through the model's OWN label_map so 中文↔id always lines up;
        # a label the model never trained on maps to -1 (sentinel) and counts as wrong,
        # never silently dropped — otherwise metrics would be inaccurate.
        mapped = df["label"].map(label2id)
        unmapped = int(mapped.isna().sum())
        y = mapped.fillna(-1).astype(int).to_numpy()
        known = list(range(len(label2id)))  # restrict averaged classes to trained labels
        p, r, f1, _ = precision_recall_fscore_support(
            y, pred, labels=known, average="macro", zero_division=0)
        out = {"accuracy": float(accuracy_score(y, pred)),
               "precision": float(p), "recall": float(r), "f1": float(f1),
               "n_samples": int(len(df))}
        if unmapped:
            out["unknown_labels"] = unmapped  # rows whose 中文 label is outside the model's label space
        # 逐条预测,供「导出预测结果表格」(worker 会把它从 metrics 里取出单独落库)。
        id2label = {v: k for k, v in label2id.items()}
        exp_label = df["label"].astype(str).tolist()
        out["predictions"] = [
            {"row": i, "input": texts[i], "expected": exp_label[i],
             "predicted": id2label.get(int(pred[i]), str(int(pred[i]))),
             "correct": bool(exp_label[i] == id2label.get(int(pred[i]), str(int(pred[i]))))}
            for i in range(len(texts))
        ]
        return out
