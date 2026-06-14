from dataclasses import dataclass, field

@dataclass
class TrainResult:
    metrics: dict
    artifact_dir: str
    label_names: list[str] = field(default_factory=list)

class Recipe:
    # on_progress(frac, metrics, step) — optional live reporter.
    # eval_df — optional held-out eval/validation set; falls back to df when None.
    def train(self, df, base_model, hyperparams, output_dir, on_progress=None, eval_df=None) -> TrainResult:
        raise NotImplementedError


def hf_progress_callback(on_progress):
    """A HuggingFace TrainerCallback that forwards (frac, metrics, step) to on_progress."""
    from transformers import TrainerCallback

    class _Cb(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kw):
            if on_progress and state.max_steps:
                try:
                    on_progress(state.global_step / state.max_steps, logs or {}, state.global_step)
                except Exception:
                    pass

    return _Cb()
