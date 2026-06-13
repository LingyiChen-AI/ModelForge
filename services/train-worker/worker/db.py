from sqlalchemy import create_engine, text, Engine
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


def load_job(engine: Engine, job_id: int) -> dict:
    """Load job details from the database."""
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT j.id, j.base_model, j.task_type, j.hyperparams, j.name, "
            "v.storage_uri FROM training_jobs j "
            "JOIN dataset_versions v ON v.id = j.dataset_version_id "
            "WHERE j.id = :id"), {"id": job_id}).mappings().one()
        return dict(row)
