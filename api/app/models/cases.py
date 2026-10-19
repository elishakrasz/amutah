import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import false as sa_false

from app.domain.enums import (
    CaseStatus,
    Category,
    ChairApprovalKind,
    ConfirmedBy,
    DocumentType,
    Tier,
)
from app.models._types import str_enum
from app.models.base import Base, MutableMixin


class AidCase(MutableMixin, Base):
    """A request for aid. Named aid_case because CASE is an SQL keyword.

    Only status, tier, assigned_coordinator_id and closed_at may change after
    insert; a trigger enforces this.
    """

    __tablename__ = "aid_case"
    __table_args__ = (CheckConstraint("amount_requested > 0", name="amount_positive"),)

    case_number: Mapped[str] = mapped_column(String(16), unique=True)  # e.g. 2026-0042
    applicant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("applicant.id"), index=True)
    referrer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("referrer.id"))
    category: Mapped[Category] = mapped_column(str_enum(Category, "category"))
    amount_requested: Mapped[int] = mapped_column(BigInteger)  # agorot
    payment_periods: Mapped[int] = mapped_column(Integer, default=1)  # > 1 means recurring
    vendor_name: Mapped[str | None] = mapped_column(String(200))
    vendor_contact: Mapped[str | None] = mapped_column(String(200))
    urgency: Mapped[bool] = mapped_column(Boolean, default=False)
    # AP-1: submitted by a referrer who was not recognised at the time.
    referral_unverified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_false()
    )
    description: Mapped[str | None] = mapped_column(Text)
    config_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("config_version.id"))

    # Mutable columns
    status: Mapped[CaseStatus] = mapped_column(str_enum(CaseStatus, "case_status"), index=True)
    tier: Mapped[Tier | None] = mapped_column(str_enum(Tier, "tier"))
    # Q20/Q26: the tier the case started at, set on the first escalation and
    # kept through A -> B -> C. Decides scoring and documents for the case.
    escalated_from_tier: Mapped[Tier | None] = mapped_column(str_enum(Tier, "escalated_from_tier"))
    assigned_coordinator_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("staff_user.id"), index=True
    )
    closed_at: Mapped[datetime | None]


CASE_MUTABLE_COLUMNS = (
    "status",
    "tier",
    "escalated_from_tier",
    "assigned_coordinator_id",
    "closed_at",
    "updated_at",
)


class CaseSequence(Base):
    """Per-year counter for case numbers."""

    __tablename__ = "case_sequence"

    year: Mapped[int] = mapped_column(Integer, unique=True)
    last_value: Mapped[int] = mapped_column(Integer, default=0)


class TierAssignment(Base):
    """Provenance for case.tier: inputs and config version it was computed from."""

    __tablename__ = "tier_assignment"
    __append_only__ = True
    __table_args__ = (CheckConstraint("band IN ('A', 'B', 'C')", name="band_is_amount_tier"),)

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    tier: Mapped[Tier] = mapped_column(str_enum(Tier, "tier"))
    band: Mapped[Tier] = mapped_column(str_enum(Tier, "band"))  # Q25: A/B/C for reporting
    amount: Mapped[int] = mapped_column(BigInteger)
    payment_periods: Mapped[int] = mapped_column(Integer)
    emergency: Mapped[bool] = mapped_column(Boolean)
    config_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("config_version.id"))


class Document(MutableMixin, Base):
    __tablename__ = "document"

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    type: Mapped[DocumentType] = mapped_column(str_enum(DocumentType, "document_type"))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)  # never exposed
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by_applicant: Mapped[bool] = mapped_column(Boolean)
    retention_until: Mapped[date | None] = mapped_column(Date)
    deleted_at: Mapped[datetime | None]


class EligibilityCheck(Base):
    __tablename__ = "eligibility_check"
    __append_only__ = True

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    category_ok: Mapped[bool] = mapped_column(Boolean)
    category_reason: Mapped[str] = mapped_column(Text)
    not_insider: Mapped[bool] = mapped_column(Boolean)
    not_insider_reason: Mapped[str] = mapped_column(Text)
    within_cap: Mapped[bool] = mapped_column(Boolean)
    within_cap_reason: Mapped[str] = mapped_column(Text)
    cooling_off_ok: Mapped[bool] = mapped_column(Boolean)
    cooling_off_reason: Mapped[str] = mapped_column(Text)
    consent_ok: Mapped[bool] = mapped_column(Boolean)
    consent_reason: Mapped[str] = mapped_column(Text)
    passed: Mapped[bool] = mapped_column(Boolean)
    config_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("config_version.id"))


class ChairApproval(Base):
    """Chair pre-approvals the gate depends on: 'other' category, cooling-off
    override for urgent cases, emergency path."""

    __tablename__ = "chair_approval"
    __append_only__ = True

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    kind: Mapped[ChairApprovalKind] = mapped_column(str_enum(ChairApprovalKind, "chair_approval"))
    reason: Mapped[str] = mapped_column(Text)


class Verification(Base):
    __tablename__ = "verification"
    __append_only__ = True

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    vendor_contacted: Mapped[str] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(String(64))
    contact_person: Mapped[str | None] = mapped_column(String(200))
    confirmed_amount: Mapped[int | None] = mapped_column(BigInteger)  # agorot
    notes: Mapped[str | None] = mapped_column(Text)


class FollowUp(Base):
    __tablename__ = "follow_up"
    __append_only__ = True

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    contacted_at: Mapped[datetime]
    outcome: Mapped[str] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    condition_met: Mapped[bool | None] = mapped_column(Boolean)  # AP-9
    condition_evidence: Mapped[str | None] = mapped_column(Text)  # AP-9
    confirmed_by: Mapped[ConfirmedBy | None] = mapped_column(  # AP-16
        str_enum(ConfirmedBy, "confirmed_by")
    )
    delivery_confirmed: Mapped[bool | None] = mapped_column(Boolean)  # AP-16


class CaseTransition(Base):
    """Every status change with its reason. The case row holds only the current status."""

    __tablename__ = "case_transition"
    __append_only__ = True

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    from_status: Mapped[CaseStatus | None] = mapped_column(str_enum(CaseStatus, "from_status"))
    to_status: Mapped[CaseStatus] = mapped_column(str_enum(CaseStatus, "to_status"))
    reason: Mapped[str] = mapped_column(Text)


class Holiday(MutableMixin, Base):
    """Israeli public holidays for working-day SLA arithmetic. Maintained by hand."""

    __tablename__ = "holiday"
    day: Mapped[date] = mapped_column(Date, unique=True)
    name_he: Mapped[str] = mapped_column(String(100))
