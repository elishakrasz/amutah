"""Declarative base and dialect-neutral column types.

Only types that behave identically on SQLite and PostgreSQL are used:
Uuid, UTCDateTime, JSON, BigInteger (money in agorot), Text, String, Boolean, Date.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, MetaData, TypeDecorator, Uuid
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes on both dialects.

    SQLite drops tzinfo on round trip; this restores it so domain code never
    sees a naive datetime.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime; use timezone-aware UTC")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        datetime: UTCDateTime(),
        dict[str, Any]: JSON,
        list[Any]: JSON,
        list[str]: JSON,
    }

    # Tables listed here get BEFORE UPDATE / BEFORE DELETE abort triggers.
    __append_only__: bool = False

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @declared_attr
    def created_by(cls) -> Mapped[uuid.UUID | None]:
        # Null only for rows created by the applicant-facing public endpoints
        # or by system jobs; the audit event names the actor in those cases.
        return mapped_column(Uuid, ForeignKey("staff_user.id"), nullable=True)


class MutableMixin:
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


def append_only_tables() -> list[str]:
    return sorted(
        mapper.class_.__tablename__
        for mapper in Base.registry.mappers
        if getattr(mapper.class_, "__append_only__", False)
    )
