from sqlalchemy import ForeignKey, UniqueConstraint, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, CreatorMixin


class Prompt(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    versions: Mapped[list["PromptVersion"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", back_populates="prompt",
        order_by="PromptVersion.version_no")

    @property
    def latest_version(self) -> "PromptVersion | None":
        return max(self.versions, key=lambda v: v.version_no) if self.versions else None

    @property
    def latest_version_no(self) -> int | None:
        lv = self.latest_version
        return lv.version_no if lv else None

    @property
    def latest_params(self) -> list:
        lv = self.latest_version
        return list(lv.params) if lv else []


class PromptVersion(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("prompt_id", "version_no",
                                       name="uq_prompt_versions_prompt_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column()
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    user_prompt: Mapped[str] = mapped_column(Text, default="")
    params: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    prompt: Mapped["Prompt"] = relationship(lazy="selectin", back_populates="versions")
