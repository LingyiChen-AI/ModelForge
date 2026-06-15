import numpy as np
from datasets import Dataset as HFDataset
from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                          TrainingArguments, Trainer, DataCollatorWithPadding)
from worker.recipes.base import Recipe, TrainResult, hf_progress_callback

def _targets(df):
    if "score" in df.columns:
        return df["score"].astype(float).tolist()
    # coerce labels to str first: merging a badcase set (str "0"/"1") with an original
    # set (int 0/1) yields a mixed-type column, and sorted() can't compare str vs int.
    s = df["label"].astype(str)
    labels = sorted(s.unique().tolist())
    l2i = {l: i for i, l in enumerate(labels)}
    return s.map(l2i).astype(float).tolist()

class PairRecipe(Recipe):
    def train(self, df, base_model, hyperparams, output_dir, on_progress=None, eval_df=None) -> TrainResult:
        max_len = int(hyperparams.get("max_length", 128))
        tok = AutoTokenizer.from_pretrained(base_model)
        def enc(b): return tok(b["text_a"], b["text_b"], truncation=True, max_length=max_len)
        def build(frame):
            d = frame.assign(labels=_targets(frame))
            return HFDataset.from_pandas(d[["text_a", "text_b", "labels"]]).map(
                enc, batched=True, remove_columns=["text_a", "text_b"])
        hf = build(df)
        eval_hf = build(eval_df) if eval_df is not None else hf
        model = AutoModelForSequenceClassification.from_pretrained(base_model, num_labels=1)
        def metrics_fn(p):
            preds = p[0].reshape(-1); y = p[1].reshape(-1)
            return {"mse": float(np.mean((preds - y) ** 2))}
        args = TrainingArguments(output_dir=output_dir,
            num_train_epochs=int(hyperparams.get("epochs", 3)),
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
        metrics = {k.replace("eval_", ""): float(v) for k, v in trainer.evaluate().items()
                   if isinstance(v, (int, float))}
        trainer.save_model(output_dir); tok.save_pretrained(output_dir)
        return TrainResult(metrics=metrics, artifact_dir=output_dir, label_names=[])
