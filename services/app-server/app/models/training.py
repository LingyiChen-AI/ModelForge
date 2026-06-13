from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from modelforge_common.enums import JobStatus


class TrainingJob(Base, TimestampMixin):
    __tablename__ = "training_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    dataset_version_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_versions.id")
    )
    base_model: Mapped[str] = mapped_column()
    task_type: Mapped[str] = mapped_column()
    hyperparams: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(default=JobStatus.PENDING.value)
    celery_task_id: Mapped[str | None] = mapped_column(nullable=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(nullable=True)


class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    source_training_job_id: Mapped[int] = mapped_column(
        ForeignKey("training_jobs.id")
    )
    mlflow_model_name: Mapped[str] = mapped_column()
    mlflow_version: Mapped[str] = mapped_column()
    task_type: Mapped[str] = mapped_column()
    base_model: Mapped[str] = mapped_column()
    train_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    stage: Mapped[str] = mapped_column(default="none")
    artifact_uri: Mapped[str | None] = mapped_column(nullable=True)


class EvalRun(Base, TimestampMixin):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id")
    )
    dataset_version_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_versions.id")
    )
    metric_config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(default=JobStatus.PENDING.value)
    celery_task_id: Mapped[str | None] = mapped_column(nullable=True)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    per_sample_uri: Mapped[str | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(nullable=True)
