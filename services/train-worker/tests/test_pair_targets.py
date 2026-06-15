import pandas as pd
from worker.recipes.pair import _targets


def test_targets_mixed_str_and_int_labels():
    # merged badcase (str) + original (int) labels must not raise on sorted()
    df = pd.DataFrame({"label": [0, 1, "0", "1"]})
    out = _targets(df)
    assert out == [0.0, 1.0, 0.0, 1.0]


def test_targets_uses_score_when_present():
    df = pd.DataFrame({"score": [0.2, 0.9], "label": ["0", "1"]})
    assert _targets(df) == [0.2, 0.9]
