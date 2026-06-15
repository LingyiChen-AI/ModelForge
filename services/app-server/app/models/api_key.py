from datetime import datetime
from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, CreatorMixin


class ApiKey(Base, TimestampMixin, CreatorMixin):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    key_prefix: Mapped[str] = mapped_column()           # "mf_" + 8 chars, for display
    key_hash: Mapped[str] = mapped_column(unique=True)  # sha256 of full plaintext key
    plaintext: Mapped[str | None] = mapped_column(nullable=True)  # stored for re-copy (convenience; null for pre-existing keys)
    scopes: Mapped[list] = mapped_column(JSON, default=list)  # ["inference","badcase:report"]
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
