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

class EmbeddingRecipe(Recipe):
    def _prepare_examples(self, df, negatives_mode="auto", model=None):
        rows = []
        corpus = [p for row in df["pos"] for p in row]
        for _, r in df.reset_index(drop=True).iterrows():
            q = r["query"]
            for pos in r["pos"]:
                negs = list(r.get("neg") or [])
                if negatives_mode == "auto" and not negs and model is not None:
                    import numpy as np
                    pool = [c for c in corpus if c not in r["pos"]]
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
        return TrainResult(metrics={"train_pairs": len(examples)},
                           artifact_dir=output_dir, label_names=[])
