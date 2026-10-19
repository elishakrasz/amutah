import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import IntakeCallOutcome, LeadStatus, RightsItem, RightsStatus
from app.models._types import str_enum
from app.models.base import Base, MutableMixin


class Lead(MutableMixin, Base):
    """AP-3: someone flagged as in need by a third party. Not a case and not an
    applicant until the subject consents. Unconverted leads expire after 90 days
    with personal fields nulled."""

    __tablename__ = "lead"
    __table_args__ = (
        CheckConstraint(
            "converted_case_id IS NULL OR consented_at IS NOT NULL", name="consent_before_case"
        ),
    )

    nominator_name: Mapped[str | None] = mapped_column(String(200))
    nominator_contact: Mapped[str | None] = mapped_column(String(200))
    subject_name: Mapped[str | None] = mapped_column(String(200))
    subject_contact: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[LeadStatus] = mapped_column(str_enum(LeadStatus, "lead_status"), index=True)
    contacted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("staff_user.id"))
    consented_at: Mapped[datetime | None]
    converted_case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("aid_case.id"))


class IntakeCall(Base):
    """AP-5: orientation call; Tier B/C need outcome=proceed before documents."""

    __tablename__ = "intake_call"
    __append_only__ = True
    __table_args__ = (CheckConstraint("duration_minutes >= 0", name="duration_non_negative"),)

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    called_at: Mapped[datetime]
    duration_minutes: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    outcome: Mapped[IntakeCallOutcome] = mapped_column(
        str_enum(IntakeCallOutcome, "intake_call_outcome")
    )
    # called_by is created_by


class RightsCheck(Base):
    """AP-7: entitlements reviewed before the amuta pays. A later, fuller check
    is a new row that supersedes the earlier one."""

    __tablename__ = "rights_check"
    __append_only__ = True

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("rights_check.id"))
    # performed_by is created_by, performed_at is created_at


class RightsCheckItem(Base):
    __tablename__ = "rights_check_item"
    __append_only__ = True

    rights_check_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rights_check.id"), index=True
    )
    item: Mapped[RightsItem] = mapped_column(str_enum(RightsItem, "item"))
    status: Mapped[RightsStatus] = mapped_column(str_enum(RightsStatus, "rights_status"))
    note: Mapped[str | None] = mapped_column(Text)


class IncomeWorksheet(Base):
    """AP-8: one standard calculation for every applicant. Money in agorot."""

    __tablename__ = "income_worksheet"
    __append_only__ = True
    __table_args__ = (
        CheckConstraint("earned_net >= 0", name="earned_non_negative"),
        CheckConstraint("btl_benefits >= 0", name="btl_non_negative"),
        CheckConstraint("other_income >= 0", name="other_non_negative"),
        CheckConstraint("household_adults >= 1", name="adults_positive"),
        CheckConstraint("household_children >= 0", name="children_non_negative"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    earned_net: Mapped[int] = mapped_column(BigInteger)
    btl_benefits: Mapped[int] = mapped_column(BigInteger)
    other_income: Mapped[int] = mapped_column(BigInteger)
    household_adults: Mapped[int] = mapped_column(Integer)
    household_children: Mapped[int] = mapped_column(Integer)
    per_person_net: Mapped[int] = mapped_column(BigInteger)  # computed by the domain
    divisor: Mapped[str] = mapped_column(String(32))  # e.g. "3.20" standard persons
    source_documents: Mapped[list[Any]] = mapped_column()  # document ids
    config_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("config_version.id"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("income_worksheet.id"))
    # prepared_by is created_by, prepared_at is created_at
