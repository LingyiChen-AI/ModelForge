from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, CreatorMixin
from modelforge_common.enums import JobStatus


class Model(Base, TimestampMixin, CreatorMixin):
    """User-named model container; each training run adds a version under it."""
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    task_type: Mapped[str] = mapped_column()
    description: Mapped[str] = mapped_column(default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class TrainingJob(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "training_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"), nullable=True)
    dataset_version_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_versions.id")
    )  # primary train version (back-compat); full selection in dataset_version_ids
    eval_dataset_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_versions.id"), nullable=True
    )  # primary eval version (back-compat); full selection in eval_dataset_version_ids
    dataset_version_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)      # merged train versions
    eval_dataset_version_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)  # merged eval versions
    base_model: Mapped[str] = mapped_column()
    task_type: Mapped[str] = mapped_column()
    hyperparams: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(default=JobStatus.PENDING.value)
    progress: Mapped[float] = mapped_column(default=0.0)  # 0~1 training progress
    celery_task_id: Mapped[str | None] = mapped_column(nullable=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    model: Mapped["Model | None"] = relationship(lazy="selectin", foreign_keys=[model_id])

    @property
    def model_name(self) -> str | None:
        return self.model.name if self.model else None

    @property
    def train_version_ids(self) -> list[int]:
        return list(self.dataset_version_ids) if self.dataset_version_ids else [self.dataset_version_id]

    @property
    def eval_version_ids(self) -> list[int]:
        if self.eval_dataset_version_ids:
            return list(self.eval_dataset_version_ids)
        return [self.eval_dataset_version_id] if self.eval_dataset_version_id else []

    def _dataset_labels(self, ids: list[int]) -> list[str]:
        from sqlalchemy import select
        from sqlalchemy.orm import object_session
        from app.models.dataset import Dataset, DatasetVersion
        db = object_session(self)
        if not db or not ids:
            return []
        rows = db.execute(
            select(DatasetVersion.id, Dataset.name, DatasetVersion.version_no)
            .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
            .where(DatasetVersion.id.in_(ids))).all()
        label = {r[0]: f"{r[1]} V{r[2]}" for r in rows}
        return [label[i] for i in ids if i in label]  # preserve selection order

    @property
    def train_datasets(self) -> list[str]:
        return self._dataset_labels(self.train_version_ids)

    @property
    def eval_datasets(self) -> list[str]:
        return self._dataset_labels(self.eval_version_ids)

    @property
    def metrics(self) -> dict:
        """Train metrics of the model version this job produced (empty until it succeeds)."""
        from sqlalchemy import select
        from sqlalchemy.orm import object_session
        db = object_session(self)
        if not db:
            return {}
        m = db.execute(
            select(ModelVersion.train_metrics)
            .where(ModelVersion.source_training_job_id == self.id)
            .order_by(ModelVersion.id.desc()).limit(1)).scalar_one_or_none()
        return m or {}


class ModelVersion(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"), nullable=True)
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
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class EvalRun(Base, TimestampMixin, CreatorMixin):
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
    progress: Mapped[float] = mapped_column(default=0.0)  # 0~1 eval progress
    celery_task_id: Mapped[str | None] = mapped_column(nullable=True)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    per_sample_uri: Mapped[str | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    model_version: Mapped["ModelVersion | None"] = relationship(lazy="selectin", foreign_keys=[model_version_id])
    dataset_version: Mapped["DatasetVersion | None"] = relationship(lazy="selectin", foreign_keys=[dataset_version_id])

    @property
    def model_name(self) -> str | None:
        return self.model_version.name if self.model_version else None

    @property
    def model_version_label(self) -> str | None:
        return self.model_version.mlflow_version if self.model_version else None

    @property
    def dataset_name(self) -> str | None:
        return self.dataset_version.dataset.name if self.dataset_version and self.dataset_version.dataset else None

    @property
    def dataset_version_no(self) -> int | None:
        return self.dataset_version.version_no if self.dataset_version else None


class Deployment(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id")
    )
    endpoint: Mapped[str | None] = mapped_column(nullable=True)
    mode: Mapped[str] = mapped_column(default="online")
    status: Mapped[str] = mapped_column(default="pending")
    replicas: Mapped[int] = mapped_column(default=1)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
