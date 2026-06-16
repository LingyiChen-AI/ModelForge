from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import badcase_contracts as bc
from app.models.badcase import Badcase
from app.models.training import ModelVersion
from app.models.dataset import Dataset
from app.services.dataset_service import create_version
from app.storage import build_storage


def stats(db: Session) -> dict:
    """Overview aggregate across all badcases: total, processed (annotated+used),
    pending, fixed (fixed_by non-empty) and the overall fix rate."""
    rows = summary(db)
    total = sum(r["reported"] for r in rows)
    processed = sum(r["annotated"] for r in rows)
    pending = sum(r["pending"] for r in rows)
    fixed = sum(r["fixed"] for r in rows)
    return {"total": total, "processed": processed, "pending": pending,
            "fixed": fixed, "fix_rate": (fixed / total) if total else 0.0}


def label_options(db: Session, model_version_id: int) -> list[str]:
    """Candidate annotation labels for a model version = the discrete label space it was
    trained on. classification -> distinct train `label`s; ner -> distinct `tags`;
    pair -> ["0","1"]; embedding -> [] (no discrete labels, annotated via pos/neg)."""
    from app.models.training import TrainingJob
    from app.models.dataset import DatasetVersion
    mv = db.get(ModelVersion, model_version_id)
    if not mv:
        raise ValueError("model_version not found")
    if mv.task_type == "pair":
        return ["0", "1"]
    if mv.task_type not in ("classification", "ner"):
        return []
    job = db.get(TrainingJob, mv.source_training_job_id) if mv.source_training_job_id else None
    if not job:
        return []
    store = build_storage()
    labels: set[str] = set()
    for vid in job.train_version_ids:
        dv = db.get(DatasetVersion, vid)
        if not dv:
            continue
        try:
            df = store.read_snapshot(dv.storage_uri)
        except Exception:
            continue  # missing/unreadable snapshot -> just contributes no labels
        if mv.task_type == "classification" and "label" in df.columns:
            labels.update(str(x) for x in df["label"].dropna().tolist())
        elif mv.task_type == "ner" and "tags" in df.columns:
            for row in df["tags"]:
                if isinstance(row, str):
                    continue
                try:
                    labels.update(str(t) for t in row)
                except TypeError:
                    continue
    return sorted(labels)


def mark_fixed(db: Session, badcase_ids: list[int], model_version_id: int, version_label: str) -> None:
    if not badcase_ids:
        return
    at = datetime.now(timezone.utc).isoformat()
    cases = list(db.execute(select(Badcase).where(Badcase.id.in_(badcase_ids))).scalars())
    for c in cases:
        existing = list(c.fixed_by or [])
        if any(e.get("model_version_id") == model_version_id for e in existing):
            continue
        existing.append({"model_version_id": model_version_id,
                         "version_label": version_label, "at": at})
        c.fixed_by = existing   # reassign so the JSON column is marked dirty
    db.commit()


def report(db: Session, body, source: str | None) -> Badcase:
    mv = db.get(ModelVersion, body.model_version_id)
    if not mv:
        raise ValueError("model_version not found")
    bc.validate_input(mv.task_type, body.input)
    if body.source_ref:  # idempotent dedup on (source, source_ref)
        existing = db.execute(select(Badcase).where(
            Badcase.source == source, Badcase.source_ref == body.source_ref)).scalar_one_or_none()
        if existing:
            return existing
    case = Badcase(model_version_id=mv.id, task_type=mv.task_type, input=body.input,
                   inference=body.inference or {}, category=bc.category_of(mv.task_type, body.inference or {}),
                   source=source, source_ref=body.source_ref, status="reported")
    db.add(case); db.commit(); db.refresh(case)
    return case


def annotate(db: Session, case_id: int, annotation: dict, user_id: int) -> Badcase:
    case = db.get(Badcase, case_id)
    if not case:
        raise ValueError("badcase not found")
    bc.validate_annotation(case.task_type, annotation)
    case.annotation = annotation
    case.status = "annotated"
    case.annotated_by = user_id
    case.annotated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(case)
    return case


def summary(db: Session) -> list[dict]:
    # Select only the columns we aggregate + the model name/version via a LEFT JOIN.
    # Avoids hydrating full Badcase ORM rows (big input/inference/annotation JSON) and the
    # cascading selectin relationship loads (ModelVersion -> dataset_version -> dataset).
    rows = db.execute(
        select(Badcase.model_version_id, Badcase.status, Badcase.task_type, Badcase.fixed_by,
               ModelVersion.name, ModelVersion.mlflow_version)
        .join(ModelVersion, ModelVersion.id == Badcase.model_version_id, isouter=True)
    ).all()
    by: dict[int, dict] = {}
    for mv_id, status, task_type, fixed_by, model_name, model_version_label in rows:
        s = by.setdefault(mv_id, {
            "model_version_id": mv_id,
            "model_name": model_name,
            "model_version_label": model_version_label,
            "task_type": task_type,
            "reported": 0, "annotated": 0, "used": 0, "pending": 0, "fixed": 0,
            "_version_counts": {}})
        s["reported"] += 1
        if status in ("annotated", "used"):
            s["annotated"] += 1
        if status == "used":
            s["used"] += 1
        if status == "reported":
            s["pending"] += 1
        if fixed_by:
            s["fixed"] += 1
            for e in fixed_by:  # one badcase may be fixed by several versions -> count toward each
                if e.get("version_label"):
                    label = str(e["version_label"])
                    s["_version_counts"][label] = s["_version_counts"].get(label, 0) + 1
    out = []
    for s in by.values():
        counts: dict = s.pop("_version_counts")
        s["fixed_versions"] = [
            {"version_label": v, "count": counts[v]}
            for v in sorted(counts, key=lambda v: (0, int(v)) if v.isdigit() else (1, v))
        ]
        out.append(s)
    return sorted(out, key=lambda x: x["model_version_id"], reverse=True)


def build_dataset(db: Session, badcase_ids: list[int], name: str | None, user_id: int):
    import pandas as pd
    if not badcase_ids:
        raise ValueError("badcase_ids required")
    cases = list(db.execute(select(Badcase).where(Badcase.id.in_(badcase_ids))).scalars())
    if len(cases) != len(set(badcase_ids)):
        raise ValueError("some badcases not found")
    task_types = {c.task_type for c in cases}
    if len(task_types) != 1:
        raise ValueError("badcases must share one task_type")
    if any(c.annotation is None for c in cases):
        raise ValueError("all badcases must be annotated first")
    task_type = task_types.pop()
    rows = [bc.to_training_row(task_type, c.input, c.annotation) for c in cases]
    df = pd.DataFrame(rows)

    ds_name = name or f"badcase-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    if not ds_name.startswith("badcase-"):
        ds_name = "badcase-" + ds_name
    ds = Dataset(name=ds_name, kind="train", task_type=task_type, created_by=user_id)
    db.add(ds); db.commit(); db.refresh(ds)
    version = create_version(db, build_storage(), ds, df, note="from badcases", created_by=user_id)
    for c in cases:
        c.status = "used"
        c.dataset_version_id = version.id
    db.commit()
    return ds, version
