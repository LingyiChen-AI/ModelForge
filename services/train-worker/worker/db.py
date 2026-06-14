import json

from sqlalchemy import create_engine, text, bindparam, Engine
from modelforge_common.enums import JobStatus
from worker.config import settings


def build_engine() -> Engine:
    """Create and return a SQLAlchemy engine."""
    return create_engine(settings.database_url, pool_pre_ping=True)


def set_job_status(engine: Engine, job_id: int, status: JobStatus,
                   mlflow_run_id: str | None = None, error: str | None = None) -> None:
    """Update job status in the database with optional mlflow_run_id and error."""
    sets = ["status = :status"]
    params = {"status": status.value, "id": job_id}
    if mlflow_run_id is not None:
        sets.append("mlflow_run_id = :mrid")
        params["mrid"] = mlflow_run_id
    if error is not None:
        sets.append("error = :err")
        params["err"] = error
    with engine.begin() as c:
        c.execute(text(f"UPDATE training_jobs SET {', '.join(sets)} WHERE id = :id"), params)


def set_job_progress(engine: Engine, job_id: int, progress: float) -> None:
    """Update live training progress (0~1) for a job."""
    with engine.begin() as c:
        c.execute(text("UPDATE training_jobs SET progress = :p WHERE id = :id"),
                  {"p": max(0.0, min(1.0, float(progress))), "id": job_id})


def _as_id_list(raw) -> list[int]:
    """JSON column comes back as a python list (PG) or a JSON string (sqlite); normalize."""
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    return [int(x) for x in raw] if isinstance(raw, list) else []


def _storage_uris(c, ids: list[int]) -> list[str]:
    """Resolve dataset_version ids -> storage_uris, preserving the given order."""
    if not ids:
        return []
    rows = c.execute(text("SELECT id, storage_uri FROM dataset_versions WHERE id IN :ids")
                     .bindparams(bindparam("ids", expanding=True)),
                     {"ids": ids}).mappings().all()
    by = {r["id"]: r["storage_uri"] for r in rows}
    return [by[i] for i in ids if i in by]


def load_job(engine: Engine, job_id: int) -> dict:
    """Load job details, resolving the merged train/eval snapshot URIs."""
    with engine.connect() as c:
        row = dict(c.execute(text(
            "SELECT j.id, j.base_model, j.task_type, j.hyperparams, j.name, "
            "j.dataset_version_id, j.eval_dataset_version_id, "
            "j.dataset_version_ids, j.eval_dataset_version_ids, "
            "m.name AS model_name, v.storage_uri, ev.storage_uri AS eval_storage_uri "
            "FROM training_jobs j "
            "JOIN dataset_versions v ON v.id = j.dataset_version_id "
            "LEFT JOIN dataset_versions ev ON ev.id = j.eval_dataset_version_id "
            "LEFT JOIN models m ON m.id = j.model_id "
            "WHERE j.id = :id"), {"id": job_id}).mappings().one())

        train_ids = _as_id_list(row.get("dataset_version_ids")) or [row["dataset_version_id"]]
        eval_ids = _as_id_list(row.get("eval_dataset_version_ids"))
        if not eval_ids and row.get("eval_dataset_version_id"):
            eval_ids = [row["eval_dataset_version_id"]]
        row["storage_uris"] = _storage_uris(c, train_ids) or [row["storage_uri"]]
        row["eval_storage_uris"] = _storage_uris(c, eval_ids)
        return row


def set_eval_status(engine: Engine, eval_run_id: int, status: JobStatus,
                    results: dict | None = None, error: str | None = None) -> None:
    """Update eval run status in the database with optional results and error."""
    sets = ["status = :status"]
    params = {"status": status.value, "id": eval_run_id}
    if results is not None:
        sets.append("results = :res")
        params["res"] = json.dumps(results)
    if error is not None:
        sets.append("error = :err")
        params["err"] = error
    with engine.begin() as c:
        c.execute(text(f"UPDATE eval_runs SET {', '.join(sets)} WHERE id = :id"), params)


def set_eval_progress(engine: Engine, eval_run_id: int, progress: float) -> None:
    """Update live eval/test progress (0~1)."""
    with engine.begin() as c:
        c.execute(text("UPDATE eval_runs SET progress = :p WHERE id = :id"),
                  {"p": max(0.0, min(1.0, float(progress))), "id": eval_run_id})


def load_eval_run(engine: Engine, eval_run_id: int) -> dict:
    """Load eval run details from the database."""
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT r.id, m.mlflow_model_name, m.mlflow_version, m.task_type, "
            "v.storage_uri, r.metric_config FROM eval_runs r "
            "JOIN model_versions m ON m.id = r.model_version_id "
            "JOIN dataset_versions v ON v.id = r.dataset_version_id "
            "WHERE r.id = :id"), {"id": eval_run_id}).mappings().one()
        return dict(row)
