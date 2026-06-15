from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, CreatorMixin


def mask_key(key: str | None) -> str:
    """脱敏展示 api_key:长度 ≤ 4 → '…';否则前 3 + '…' + 后 4。"""
    if not key:
        return ""
    if len(key) <= 4:
        return "…"
    return key[:3] + "…" + key[-4:]


class LlmProvider(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    base_url: Mapped[str] = mapped_column()
    api_key: Mapped[str] = mapped_column()          # 明文存;响应只出 masked_key
    enabled: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    models: Mapped[list["LlmModel"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", back_populates="provider")

    @property
    def masked_key(self) -> str:
        return mask_key(self.api_key)


class LlmModel(Base, TimestampMixin):
    __tablename__ = "llm_models"
    __table_args__ = (UniqueConstraint("provider_id", "model_id",
                                       name="uq_llm_models_provider_model"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("llm_providers.id", ondelete="CASCADE"))
    model_id: Mapped[str] = mapped_column()
    provider: Mapped["LlmProvider"] = relationship(lazy="selectin", back_populates="models")
