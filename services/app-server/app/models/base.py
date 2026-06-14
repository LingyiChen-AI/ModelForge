from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, declared_attr, relationship,
)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class CreatorMixin:
    """For models with a ``created_by`` FK to users.

    Adds a lazy ``creator`` relationship and a ``created_by_name`` property so
    schemas can serialize the creator's display name without an N+1 query.
    The owning model still declares its own ``created_by`` column.
    """

    @declared_attr
    def creator(cls):
        return relationship(
            "User", lazy="selectin", viewonly=True,
            foreign_keys=lambda: [cls.created_by],
        )

    @property
    def created_by_name(self) -> str | None:
        return self.creator.name if self.creator else None
