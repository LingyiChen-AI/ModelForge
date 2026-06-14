"""Per-task-type badcase contracts: report-input / inference / annotation shapes,
the mapping from an annotated badcase to a training row, and the read-only rules."""

INPUT_KEYS = {
    "classification": ["text"],
    "ner": ["tokens"],
    "pair": ["text_a", "text_b"],
    "embedding": ["query", "candidates"],
}
ANNOTATION_KEYS = {
    "classification": ["label"],
    "ner": ["tags"],
    "pair": ["label"],
    "embedding": ["pos"],   # neg optional
}
TASK_TYPES = list(INPUT_KEYS)


def _require(d: dict, keys: list[str], what: str) -> None:
    if not isinstance(d, dict):
        raise ValueError(f"{what} must be an object")
    missing = [k for k in keys if k not in d or d[k] in (None, "")]
    if missing:
        raise ValueError(f"{what} missing fields: {missing}")


def validate_input(task_type: str, input: dict) -> None:
    if task_type not in INPUT_KEYS:
        raise ValueError(f"unknown task_type: {task_type}")
    _require(input, INPUT_KEYS[task_type], "input")
    if task_type == "embedding" and not input.get("candidates"):
        raise ValueError("input.candidates must be a non-empty list")


def validate_annotation(task_type: str, annotation: dict) -> None:
    if task_type not in ANNOTATION_KEYS:
        raise ValueError(f"unknown task_type: {task_type}")
    _require(annotation, ANNOTATION_KEYS[task_type], "annotation")
    if task_type == "embedding" and not annotation.get("pos"):
        raise ValueError("annotation.pos must be a non-empty list")


def to_training_row(task_type: str, input: dict, annotation: dict) -> dict:
    if task_type == "classification":
        return {"text": input["text"], "label": annotation["label"]}
    if task_type == "ner":
        return {"tokens": input["tokens"], "tags": annotation["tags"]}
    if task_type == "pair":
        return {"text_a": input["text_a"], "text_b": input["text_b"], "label": annotation["label"]}
    if task_type == "embedding":
        return {"query": input["query"], "pos": annotation["pos"], "neg": annotation.get("neg", [])}
    raise ValueError(f"unknown task_type: {task_type}")


def category_of(task_type: str, inference: dict) -> str | None:
    if task_type == "classification" and isinstance(inference, dict):
        return inference.get("label")
    return None


_EXAMPLES = {
    "classification": {"input": {"text": "怎么退货"}, "inference": {"label": "物流查询", "score": 0.82},
                       "annotation": {"label": "售后服务"}},
    "ner": {"input": {"tokens": ["小", "明", "在", "北", "京"]}, "inference": {"tags": ["O", "O", "O", "O", "O"]},
            "annotation": {"tags": ["B-PER", "I-PER", "O", "B-LOC", "I-LOC"]}},
    "pair": {"input": {"text_a": "今天天气如何", "text_b": "明天会下雨吗"}, "inference": {"score": 0.88},
             "annotation": {"label": "0"}},
    "embedding": {"input": {"query": "如何重置密码", "candidates": ["在设置页重置密码", "联系客服热线"]},
                  "inference": {"ranked": [{"text": "联系客服热线", "score": 0.71}, {"text": "在设置页重置密码", "score": 0.63}]},
                  "annotation": {"pos": ["在设置页重置密码"], "neg": ["联系客服热线"]}},
}


def rules() -> list[dict]:
    out = []
    for t in TASK_TYPES:
        out.append({
            "task_type": t,
            "input_keys": INPUT_KEYS[t],
            "annotation_keys": ANNOTATION_KEYS[t] + (["neg(可选)"] if t == "embedding" else []),
            "example": _EXAMPLES[t],
        })
    return out
