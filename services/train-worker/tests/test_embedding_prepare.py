import numpy as np
from worker.recipes.embedding import _as_list


def test_as_list_handles_numpy_array():
    # numpy array (how parquet hands back list columns) must not raise on bool/`or`
    assert _as_list(np.array(["a", "b"])) == ["a", "b"]
    assert _as_list(np.array([])) == []
    assert _as_list(["x"]) == ["x"]
    assert _as_list(None) == []
    assert _as_list(float("nan")) == []   # missing cell
