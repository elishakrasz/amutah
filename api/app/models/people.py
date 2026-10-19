import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import InsiderRelationship, Language, ReferrerStatus
from app.models._types import str_enum
from app.models.base import Base, MutableMixin


class StaffUser(MutableMixin, Base):
    __tablename__ = "staff_user"

    display_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    # Role values from app.domain.enums.Role. Production mirrors Entra app roles.
    roles: Mapped[list[Any]] = mapped_column()
    entra_object_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Household(MutableMixin, Base):
    """Groups applicants who share a household, for caps."""

    __tablename__ = "household"


class Applicant(MutableMixin, Base):
    __tablename__ = "applicant"
    __table_args__ = (
        CheckConstraint("household_adults >= 1", name="adults_positive"),
        CheckConstraint("household_children >= 0", name="children_non_negative"),
    )

    # Keyed HMAC for lookup and encrypted value for display. Never logged.
    national_id_hash: Mapped[str] = mapped_column(String(64), unique=True)
    national_id_enc: Mapped[str | None] = mapped_column(Text)
    # Partner's ID, hashed only: used to derive the household and run the insider check.
    partner_national_id_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    household_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("household.id"))

    # Personal fields are nullable so the retention job can null them.
    name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    address: Mapped[str | None] = mapped_column(Text)
    household_adults: Mapped[int] = mapped_column(Integer)
    household_children: Mapped[int] = mapped_column(Integer)

    consent_at: Mapped[datetime]
    consent_version: Mapped[str] = mapped_column(String(32))
    preferred_language: Mapped[Language] = mapped_column(  # AP-4
        str_enum(Language, "preferred_language"), default=Language.HE, server_default="he"
    )


class Referrer(MutableMixin, Base):
    """AP-1: a referral counts as referred only while status is recognised."""

    __tablename__ = "referrer"

    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200))
    organisation: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[ReferrerStatus] = mapped_column(
        str_enum(ReferrerStatus, "referrer_status"),
        default=ReferrerStatus.PENDING,
        server_default="pending",
    )
    recognised_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("staff_user.id"))
    recognised_at: Mapped[datetime | None]
    organisation_verified_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("staff_user.id")
    )
    organisation_verified_at: Mapped[datetime | None]
    manager_name: Mapped[str | None] = mapped_column(String(200))
    manager_contact: Mapped[str | None] = mapped_column(String(200))


class Insider(MutableMixin, Base):
    """People who can never receive aid. Maintained from board resolutions."""

    __tablename__ = "insider"

    national_id_hash: Mapped[str] = mapped_column(String(64), index=True)
    relationship: Mapped[InsiderRelationship] = mapped_column(
        str_enum(InsiderRelationship, "insider_relationship")
    )
    source: Mapped[str] = mapped_column(Text)  # board resolution reference
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
