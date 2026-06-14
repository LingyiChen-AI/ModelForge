from sqlalchemy import ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, CreatorMixin


class Dataset(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    kind: Mapped[str] = mapped_column()        # DatasetKind
    task_type: Mapped[str] = mapped_column()   # TaskType
    schema_: Mapped[dict] = mapped_column("schema", JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    versions: Mapped[list["DatasetVersion"]] = relationship(
        back_populates="dataset"
    )


class DatasetVersion(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    version_no: Mapped[int] = mapped_column()
    storage_uri: Mapped[str] = mapped_column()
    row_count: Mapped[int] = mapped_column()
    checksum: Mapped[str] = mapped_column()
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(default="")
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    dataset: Mapped["Dataset"] = relationship(back_populates="versions")
