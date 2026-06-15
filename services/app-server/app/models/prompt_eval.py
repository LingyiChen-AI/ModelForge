from datetime import datetime
from sqlalchemy import ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, CreatorMixin


class PromptEvalRun(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "prompt_eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    eval_type: Mapped[str] = mapped_column()        # multi_prompt / multi_model / single_prompt
    status: Mapped[str] = mapped_column(default="pending")
    progress: Mapped[float] = mapped_column(default=0.0)
    celery_task_id: Mapped[str | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(nullable=True)
    prompt_version_ids: Mapped[list] = mapped_column(JSON, default=list)
    model_ids: Mapped[list] = mapped_column(JSON, default=list)
    dataset_version_ids: Mapped[list] = mapped_column(JSON, default=list)
    compare_to_version_id: Mapped[int | None] = mapped_column(nullable=True)
    result_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    arms: Mapped[list["PromptEvalArm"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", back_populates="run",
        order_by="PromptEvalArm.arm_index")


class PromptEvalArm(Base, TimestampMixin):
    __tablename__ = "prompt_eval_arms"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("prompt_eval_runs.id", ondelete="CASCADE"))
    arm_index: Mapped[int] = mapped_column()
    prompt_version_id: Mapped[int] = mapped_column(ForeignKey("prompt_versions.id"))
    model_id: Mapped[int] = mapped_column(ForeignKey("llm_models.id"))
    label: Mapped[str] = mapped_column(default="")
    run: Mapped["PromptEvalRun"] = relationship(lazy="selectin", back_populates="arms")


class PromptEvalItem(Base, TimestampMixin):
    __tablename__ = "prompt_eval_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("prompt_eval_runs.id", ondelete="CASCADE"))
    item_index: Mapped[int] = mapped_column()
    dataset_version_id: Mapped[int] = mapped_column()
    row_index: Mapped[int] = mapped_column()
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    winner_arm_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_eval_arms.id"), nullable=True)
    all_bad: Mapped[bool] = mapped_column(default=False)
    is_good: Mapped[bool | None] = mapped_column(nullable=True)
    evaluated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    outputs: Mapped[list["PromptEvalOutput"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", back_populates="item",
        order_by="PromptEvalOutput.id")
    annotator: Mapped["User | None"] = relationship(  # type: ignore  # noqa: F821
        "User", lazy="selectin", viewonly=True, foreign_keys=[evaluated_by])

    @property
    def annotated_by_name(self) -> str | None:
        return self.annotator.name if self.annotator else None


class PromptEvalOutput(Base, TimestampMixin):
    __tablename__ = "prompt_eval_outputs"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("prompt_eval_items.id", ondelete="CASCADE"))
    arm_id: Mapped[int] = mapped_column(ForeignKey("prompt_eval_arms.id"))
    output_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(default="pending")   # pending / done / error
    error: Mapped[str | None] = mapped_column(nullable=True)
    latency_ms: Mapped[int] = mapped_column(default=0)
    item: Mapped["PromptEvalItem"] = relationship(lazy="selectin", back_populates="outputs")
