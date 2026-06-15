import io, json
import pandas as pd
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from modelforge_common.enums import TaskType, DatasetKind
from app.models.dataset import Dataset, DatasetVersion
from app.storage import SnapshotStorage


REQUIRED_COLUMNS = {
    TaskType.CLASSIFICATION: ["text", "label"],
    TaskType.NER: ["tokens", "tags"],
    TaskType.PAIR: ["text_a", "text_b"],
    TaskType.EMBEDDING: ["query", "pos"],
}

# Columns whose values are lists. In CSV / Excel these arrive as JSON strings
# and must be parsed back into lists before the parquet snapshot is written.
LIST_COLUMNS = {
    TaskType.NER: ["tokens", "tags"],
    TaskType.EMBEDDING: ["pos", "neg"],
}

# Example rows per task type, used both for the downloadable template and docs.
TEMPLATE_ROWS = {
    # 多分类:标签数量任意,训练时按数据里出现的 label 自动建类别。
    TaskType.CLASSIFICATION: [
        {"text": "这个商品什么时候能发货", "label": "物流查询"},
        {"text": "我想退货应该怎么操作", "label": "售后服务"},
        {"text": "这款和那款有什么区别", "label": "售前咨询"},
        {"text": "等了好久都没人回复我", "label": "投诉建议"},
    ],
    TaskType.NER: [
        {"tokens": ["小", "明", "在", "北", "京", "工", "作"],
         "tags": ["B-PER", "I-PER", "O", "B-LOC", "I-LOC", "O", "O"]},
        {"tokens": ["李", "雷", "来", "自", "上", "海"],
         "tags": ["B-PER", "I-PER", "O", "O", "B-LOC", "I-LOC"]},
    ],
    TaskType.PAIR: [
        {"text_a": "今天天气怎么样", "text_b": "今天的天气如何", "label": "1"},
        {"text_a": "我想订机票", "text_b": "附近有什么好吃的", "label": "0"},
    ],
    TaskType.EMBEDDING: [
        {"query": "如何重置密码", "pos": ["在设置页点击重置密码"], "neg": ["请联系客服热线"]},
        {"query": "怎么开发票", "pos": ["在订单详情页申请开票"], "neg": ["配送通常需要三天"]},
    ],
}


def validate_rows(df: pd.DataFrame, task_type: TaskType) -> None:
    required = REQUIRED_COLUMNS[task_type]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns for {task_type.value}: {missing}")
    if len(df) == 0:
        raise ValueError("dataset is empty")


def validate_prompt_rows(df: pd.DataFrame) -> None:
    if df.shape[1] == 0:
        raise ValueError("Prompt 测试集至少需要一列参数")
    if len(df) == 0:
        raise ValueError("dataset is empty")


def _parse_list_cell(v):
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except (ValueError, TypeError):
            return v
    return v


def normalize_list_columns(df: pd.DataFrame, task_type: TaskType) -> pd.DataFrame:
    """Parse JSON-string list columns (from CSV / Excel) back into real lists."""
    for col in LIST_COLUMNS.get(task_type, []):
        if col in df.columns:
            df[col] = df[col].map(_parse_list_cell)
    return df


def template_dataframe(task_type: TaskType) -> pd.DataFrame:
    return pd.DataFrame(TEMPLATE_ROWS[task_type])


def serialize_df(df: pd.DataFrame, task_type: TaskType, fmt: str) -> tuple[bytes, str, str]:
    """Serialize a version's snapshot DataFrame for download (bytes, media_type, ext)."""
    if fmt == "jsonl":
        # pandas serializes list columns as JSON arrays natively
        return (df.to_json(orient="records", lines=True, force_ascii=False).encode("utf-8"),
                "application/x-ndjson", "jsonl")
    flat = df.copy()
    for col in LIST_COLUMNS.get(task_type, []):
        if col in flat.columns:
            flat[col] = flat[col].map(
                lambda x: "" if x is None or (isinstance(x, float) and pd.isna(x))
                else json.dumps(list(x), ensure_ascii=False))
    if fmt == "csv":
        return (flat.to_csv(index=False).encode("utf-8-sig"), "text/csv", "csv")
    if fmt == "xlsx":
        buf = io.BytesIO()
        flat.to_excel(buf, index=False)
        return (buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx")
    raise ValueError("fmt must be csv | jsonl | xlsx")


def serialize_template(task_type: TaskType, fmt: str) -> tuple[bytes, str, str]:
    """Return (bytes, media_type, ext) for a task-type template in the given format."""
    df = template_dataframe(task_type)
    if fmt == "jsonl":
        lines = [json.dumps(row, ensure_ascii=False) for row in df.to_dict(orient="records")]
        return ("\n".join(lines).encode("utf-8"), "application/x-ndjson", "jsonl")
    # CSV / Excel can't hold arrays — JSON-encode list columns into string cells.
    flat = df.copy()
    for col in LIST_COLUMNS.get(task_type, []):
        if col in flat.columns:
            flat[col] = flat[col].map(lambda x: json.dumps(x, ensure_ascii=False))
    if fmt == "csv":
        # utf-8-sig so Excel renders CJK correctly.
        return (flat.to_csv(index=False).encode("utf-8-sig"), "text/csv", "csv")
    if fmt == "xlsx":
        buf = io.BytesIO()
        flat.to_excel(buf, index=False)
        return (buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx")
    raise ValueError("fmt must be csv | jsonl | xlsx")


def create_version(db: Session, store: SnapshotStorage, dataset: Dataset,
                   df: pd.DataFrame, note: str = "",
                   created_by: int | None = None) -> DatasetVersion:
    if dataset.kind == DatasetKind.PROMPT.value:
        validate_prompt_rows(df)
    else:
        validate_rows(df, TaskType(dataset.task_type))
        df = normalize_list_columns(df, TaskType(dataset.task_type))
    next_no = (db.execute(
        select(func.coalesce(func.max(DatasetVersion.version_no), 0))
        .where(DatasetVersion.dataset_id == dataset.id)).scalar()) + 1
    uri, checksum, rows = store.write_snapshot(dataset.id, next_no, df)
    version = DatasetVersion(
        dataset_id=dataset.id, version_no=next_no, storage_uri=uri,
        row_count=rows, checksum=checksum, note=note,
        stats={"columns": list(df.columns)}, created_by=created_by)
    db.add(version)
    db.commit()
    db.refresh(version)
    return version
