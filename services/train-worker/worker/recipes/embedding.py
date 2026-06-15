from sentence_transformers import SentenceTransformer, models, InputExample, losses
from torch.utils.data import DataLoader
from worker.recipes.base import Recipe, TrainResult

def _build_st(base_model: str) -> SentenceTransformer:
    # trust_remote_code lets custom-architecture embedding models (e.g. the
    # Alibaba-NLP/gte-*-v1.5 family) load their modeling code from the curated hub repo.
    trust = {"trust_remote_code": True}
    word = models.Transformer(
        base_model, max_seq_length=128,
        config_args=trust, model_args=trust, tokenizer_args=trust,
    )
    pool = models.Pooling(word.get_word_embedding_dimension(), pooling_mode="mean")
    return SentenceTransformer(modules=[word, pool])

def _as_list(v):
    """Coerce a parquet list-cell to a plain list. pandas hands list columns back as
    numpy arrays, so `v or []` / `if v` would raise 'truth value of an array is ambiguous'."""
    if v is None:
        return []
    try:
        return list(v)
    except TypeError:
        return []


class EmbeddingRecipe(Recipe):
    def _prepare_examples(self, df, negatives_mode="auto", model=None):
        import numpy as np
        rows = []
        corpus = [p for row in df["pos"] for p in _as_list(row)]
        for _, r in df.reset_index(drop=True).iterrows():
            q = r["query"]
            pos_list = _as_list(r["pos"])
            for pos in pos_list:
                negs = _as_list(r.get("neg"))
                if negatives_mode == "auto" and not negs and model is not None:
                    pool = [c for c in corpus if c not in pos_list]
                    if pool:
                        qe = model.encode([q]); ce = model.encode(pool)
                        sims = (qe @ ce.T)[0]
                        negs = [pool[int(np.argmax(sims))]]
                if negs:
                    rows.append(InputExample(texts=[q, pos, negs[0]]))
                else:
                    rows.append(InputExample(texts=[q, pos]))
        return rows

    def train(self, df, base_model, hyperparams, output_dir, on_progress=None, eval_df=None) -> TrainResult:
        model = _build_st(base_model)
        mode = (hyperparams.get("negatives") or {}).get("mode", "auto")
        examples = self._prepare_examples(df, negatives_mode=mode, model=model)
        loader = DataLoader(examples, shuffle=True,
                            batch_size=int(hyperparams.get("batch_size", 16)))
        loss = losses.MultipleNegativesRankingLoss(model)
        # sentence-transformers .fit has no per-step hook — report coarse start;
        # the task marks 100% on completion.
        if on_progress:
            try: on_progress(0.1, {}, 0)
            except Exception: pass
        model.fit(train_objectives=[(loader, loss)],
                  epochs=int(hyperparams.get("epochs", 1)), warmup_steps=0,
                  show_progress_bar=False)
        model.save(output_dir)
        metrics = {"train_pairs": len(examples)}
        # Report retrieval quality on the held-out eval set (recall@1/3/5) so the model's
        # metrics are meaningful — not just a pair count. Mirrors how the other recipes
        # surface eval metrics from their validation set.
        if eval_df is not None and len(eval_df) > 0:
            from worker.evaluators.embedding import EmbeddingEvaluator
            try:
                ev = EmbeddingEvaluator().evaluate(output_dir, eval_df)
                metrics.update({k: v for k, v in ev.items() if k.startswith("recall@")})
            except Exception:
                pass
        return TrainResult(metrics=metrics, artifact_dir=output_dir, label_names=[])
