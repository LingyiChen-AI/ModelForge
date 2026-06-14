from worker.tasks import _mlflow_metrics


def test_sanitizes_at_sign():
    # MLflow rejects '@'; it must be replaced for MLflow logging.
    out = _mlflow_metrics({"recall@1": 0.3, "recall@3": 0.7, "recall@5": 0.9, "accuracy": 0.967})
    assert out == {"recall_at_1": 0.3, "recall_at_3": 0.7, "recall_at_5": 0.9, "accuracy": 0.967}


def test_drops_non_numeric_keeps_allowed_chars():
    out = _mlflow_metrics({"f1": 0.5, "n_samples": 10, "note": "x", "a/b:c": 1.0})
    # str value dropped; int coerced to float; '/' and ':' are allowed by MLflow → kept
    assert out == {"f1": 0.5, "n_samples": 10.0, "a/b:c": 1.0}
