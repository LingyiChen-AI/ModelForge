from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import badcase_contracts as bc
from app.models.badcase import Badcase
from app.models.training import ModelVersion
from app.models.dataset import Dataset
from app.services.dataset_service import create_version
from app.storage import build_storage


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
