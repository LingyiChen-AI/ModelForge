import numpy as np
import torch


class Evaluator:
    # on_progress(frac: float) — optional 0~1 inference progress reporter.
    def evaluate(self, model_dir: str, df, on_progress=None) -> dict:
        raise NotImplementedError


def batched_logits(model, encode, n, on_progress=None, batch=32):
    """Run inference in batches, reporting progress; encode(i, j) -> tokenized rows [i:j)."""
    outs = []
    for i in range(0, n, batch):
        with torch.no_grad():
            outs.append(model(**encode(i, min(i + batch, n))).logits.cpu().numpy())
        if on_progress:
            try:
                on_progress(min(i + batch, n) / max(1, n))
            except Exception:
                pass
    return np.concatenate(outs, axis=0) if outs else np.zeros((0, 1))
