import json, os
import numpy as np
from datasets import Dataset as HFDataset
from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                          TrainingArguments, Trainer, DataCollatorWithPadding)
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from worker.recipes.base import Recipe, TrainResult, hf_progress_callback

class ClassificationRecipe(Recipe):
    def train(self, df, base_model, hyperparams, output_dir, on_progress=None, eval_df=None) -> TrainResult:
        labels = sorted(df["label"].unique().tolist())
        label2id = {l: i for i, l in enumerate(labels)}
        df = df.assign(_y=df["label"].map(label2id))
        max_len = int(hyperparams.get("max_length", 128))

        tok = AutoTokenizer.from_pretrained(base_model)
        def tok_fn(b): return tok(b["text"], truncation=True, max_length=max_len)
        def build(frame):
            f = frame.assign(_y=frame["label"].map(label2id)).dropna(subset=["_y"])
            f = f.assign(_y=f["_y"].astype(int))
            return HFDataset.from_pandas(f[["text", "_y"]].rename(columns={"_y": "labels"})).map(tok_fn, batched=True)
        hf = build(df)
        # held-out eval set if provided (labels mapped via train's label space)
        eval_hf = build(eval_df) if eval_df is not None else hf

        model = AutoModelForSequenceClassification.from_pretrained(
            base_model, num_labels=len(labels),
            id2label={i: l for l, i in label2id.items()}, label2id=label2id)

        def metrics_fn(eval_pred):
            logits, y = eval_pred
            pred = np.argmax(logits, axis=-1)
            p, r, f1, _ = precision_recall_fscore_support(y, pred, average="macro", zero_division=0)
            return {"accuracy": accuracy_score(y, pred), "precision": p, "recall": r, "f1": f1}

        args = TrainingArguments(
            output_dir=output_dir, num_train_epochs=int(hyperparams.get("epochs", 3)),
            per_device_train_batch_size=int(hyperparams.get("batch_size", 16)),
            per_device_eval_batch_size=int(hyperparams.get("batch_size", 16)),
            learning_rate=float(hyperparams.get("lr", 5e-5)),
            report_to=[], logging_steps=10, save_strategy="no")
        trainer = Trainer(model=model, args=args, train_dataset=hf, eval_dataset=eval_hf,
                          compute_metrics=metrics_fn,
                          data_collator=DataCollatorWithPadding(tok))
        if on_progress:
            trainer.add_callback(hf_progress_callback(on_progress))
        trainer.train()
        metrics = trainer.evaluate()
        metrics = {k.replace("eval_", ""): v for k, v in metrics.items()}

        trainer.save_model(output_dir)
        tok.save_pretrained(output_dir)
        with open(os.path.join(output_dir, "label_map.json"), "w") as f:
            json.dump(label2id, f)
        return TrainResult(metrics=metrics, artifact_dir=output_dir, label_names=labels)
