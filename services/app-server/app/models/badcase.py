from datetime import datetime
from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class Badcase(Base, TimestampMixin):
    __tablename__ = "badcases"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"))
    task_type: Mapped[str] = mapped_column()
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    inference: Mapped[dict] = mapped_column(JSON, default=dict)
    category: Mapped[str | None] = mapped_column(nullable=True)
    source: Mapped[str | None] = mapped_column(nullable=True)
    source_ref: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default="reported")  # reported|annotated|used
    annotation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    annotated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    annotated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    dataset_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_versions.id"), nullable=True)
    fixed_by: Mapped[list] = mapped_column(JSON, default=list)  # [{model_version_id, version_label, at}]
    model_version: Mapped["ModelVersion | None"] = relationship(  # type: ignore  # noqa: F821
        "ModelVersion", lazy="selectin", foreign_keys=[model_version_id])

    @property
    def model_name(self) -> str | None:
        return self.model_version.name if self.model_version else None

    @property
    def model_version_label(self) -> str | None:
        return self.model_version.mlflow_version if self.model_version else None

    @property
    def is_fixed(self) -> bool:
        return bool(self.fixed_by)
