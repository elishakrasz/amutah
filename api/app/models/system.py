import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import ActorType, OrgDocumentType
from app.models._types import str_enum
from app.models.base import Base, MutableMixin


class ConfigVersion(Base):
    """Board-controlled rules configuration. Every derived value cites one."""

    __tablename__ = "config_version"
    __append_only__ = True

    version: Mapped[int] = mapped_column(Integer, unique=True)
    body: Mapped[dict[str, Any]] = mapped_column()  # tiers, caps, cooling-off, thresholds, ...
    approved_by: Mapped[list[str]] = mapped_column()  # board member staff_user ids
    board_resolution: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[datetime]


class AuditEvent(Base):
    """Written by the application in the same transaction as the change it records.
    Triggers make it immutable; production also withholds UPDATE/DELETE grants."""

    __tablename__ = "audit_event"
    __append_only__ = True

    actor_type: Mapped[ActorType] = mapped_column(str_enum(ActorType, "actor_type"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # staff_user or applicant id
    role: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    purpose: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(45))
    detail: Mapped[dict[str, Any] | None] = mapped_column()


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"

    key: Mapped[str] = mapped_column(String(128), unique=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(512))
    request_sha256: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[str] = mapped_column(Text)


class OtpChallenge(Base):
    __tablename__ = "otp_challenge"

    applicant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("applicant.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime]
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None]


class OrgDocument(MutableMixin, Base):
    """AP-18: public organisational documents. Admin uploads; public reads
    only rows with published = true."""

    __tablename__ = "org_document"

    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[OrgDocumentType] = mapped_column(str_enum(OrgDocumentType, "org_document_type"))
    year: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    content_type: Mapped[str] = mapped_column(String(128))
    sha256: Mapped[str] = mapped_column(String(64))
    published: Mapped[bool] = mapped_column(Boolean, default=False)


class PublicStatsPublication(Base):
    """AP-17: nothing is public for a quarter until a board member publishes it."""

    __tablename__ = "public_stats_publication"
    __append_only__ = True
    __table_args__ = (CheckConstraint("quarter BETWEEN 1 AND 4", name="quarter_range"),)

    year: Mapped[int] = mapped_column(Integer)
    quarter: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column()  # the exact figures published
    config_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("config_version.id"))
    # published_by is created_by, published_at is created_at
