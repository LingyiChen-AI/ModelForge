import json, os
import numpy as np
from datasets import Dataset as HFDataset
from transformers import (AutoTokenizer, AutoModelForTokenClassification,
                          TrainingArguments, Trainer, DataCollatorForTokenClassification)
from seqeval.metrics import accuracy_score, f1_score, precision_score, recall_score
from worker.recipes.base import Recipe, TrainResult

class NERRecipe(Recipe):
    def train(self, df, base_model, hyperparams, output_dir) -> TrainResult:
        tag_set = sorted({t for row in df["tags"] for t in row})
        tag2id = {t: i for i, t in enumerate(tag_set)}
        id2tag = {i: t for t, i in tag2id.items()}
        max_len = int(hyperparams.get("max_length", 128))
        tok = AutoTokenizer.from_pretrained(base_model)

        def encode(batch):
            enc = tok(batch["tokens"], is_split_into_words=True, truncation=True,
                      max_length=max_len)
            labels = []
            for i, tags in enumerate(batch["tags"]):
                word_ids = enc.word_ids(batch_index=i)
                prev, seq = None, []
                for wid in word_ids:
                    if wid is None:
                        seq.append(-100)
                    elif wid != prev:
                        seq.append(tag2id[tags[wid]])
                    else:
                        seq.append(-100)
                    prev = wid
                labels.append(seq)
            enc["labels"] = labels
            return enc

        hf = HFDataset.from_pandas(df[["tokens", "tags"]])
        hf = hf.map(encode, batched=True, remove_columns=hf.column_names)
        model = AutoModelForTokenClassification.from_pretrained(
            base_model, num_labels=len(tag_set), id2label=id2tag, label2id=tag2id)
        collator = DataCollatorForTokenClassification(tok)

        def metrics_fn(p):
            logits, labels = p
            preds = np.argmax(logits, axis=-1)
            true, pred = [], []
            for pr, la in zip(preds, labels):
                t_seq, p_seq = [], []
                for pi, li in zip(pr, la):
                    if li != -100:
                        t_seq.append(id2tag[int(li)]); p_seq.append(id2tag[int(pi)])
                true.append(t_seq); pred.append(p_seq)
            return {"accuracy": accuracy_score(true, pred), "precision": precision_score(true, pred),
                    "recall": recall_score(true, pred), "f1": f1_score(true, pred)}

        args = TrainingArguments(output_dir=output_dir,
            num_train_epochs=int(hyperparams.get("epochs", 3)),
            per_device_train_batch_size=int(hyperparams.get("batch_size", 16)),
            per_device_eval_batch_size=int(hyperparams.get("batch_size", 16)),
            learning_rate=float(hyperparams.get("lr", 5e-5)),
            report_to=[], logging_steps=10, save_strategy="no")
        trainer = Trainer(model=model, args=args, train_dataset=hf, eval_dataset=hf,
                          data_collator=collator, compute_metrics=metrics_fn)
        trainer.train()
        metrics = {k.replace("eval_", ""): float(v) for k, v in trainer.evaluate().items()
                   if isinstance(v, (int, float))}
        trainer.save_model(output_dir); tok.save_pretrained(output_dir)
        with open(os.path.join(output_dir, "tag_map.json"), "w") as f:
            json.dump(tag2id, f)
        return TrainResult(metrics=metrics, artifact_dir=output_dir, label_names=tag_set)
