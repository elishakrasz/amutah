import uuid

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import AppealOutcome, BalanceSource, ConditionType, DecisionOutcome
from app.models._types import str_enum
from app.models.base import Base


class Score(Base):
    __tablename__ = "score"
    __append_only__ = True
    __table_args__ = (
        CheckConstraint("need BETWEEN 0 AND 3", name="need_range"),
        CheckConstraint("urgency BETWEEN 0 AND 3", name="urgency_range"),
        CheckConstraint("impact BETWEEN 0 AND 3", name="impact_range"),
        CheckConstraint("alternatives BETWEEN 0 AND 3", name="alternatives_range"),
        CheckConstraint("vulnerability BETWEEN 0 AND 1", name="vulnerability_range"),
        CheckConstraint(
            "total = need + urgency + impact + alternatives + vulnerability", name="total_sum"
        ),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    committee_member_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("staff_user.id"))
    need: Mapped[int] = mapped_column(Integer)
    urgency: Mapped[int] = mapped_column(Integer)
    impact: Mapped[int] = mapped_column(Integer)
    alternatives: Mapped[int] = mapped_column(Integer)
    vulnerability: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    config_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("config_version.id"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("score.id"))


class Recusal(Base):
    __tablename__ = "recusal"
    __append_only__ = True

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    committee_member_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("staff_user.id"))
    reason: Mapped[str] = mapped_column(Text)


class Decision(Base):
    __tablename__ = "decision"
    __append_only__ = True
    __table_args__ = (
        CheckConstraint("amount_approved >= 0", name="amount_non_negative"),
        CheckConstraint(
            "exception_flag = false OR length(trim(reasoning)) > 0", name="exception_reasoned"
        ),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    outcome: Mapped[DecisionOutcome] = mapped_column(str_enum(DecisionOutcome, "decision_outcome"))
    amount_approved: Mapped[int] = mapped_column(BigInteger)  # agorot
    conditions: Mapped[str | None] = mapped_column(Text)
    condition_type: Mapped[ConditionType | None] = mapped_column(  # AP-7, AP-9
        str_enum(ConditionType, "condition_type")
    )
    # AP-12: how the unfunded part of a partial approval is covered.
    balance_source: Mapped[BalanceSource | None] = mapped_column(
        str_enum(BalanceSource, "balance_source")
    )
    balance_evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document.id")
    )
    reasoning: Mapped[str] = mapped_column(Text, default="")
    # Guideline the engine recommended, kept for provenance.
    guideline_outcome: Mapped[str | None] = mapped_column(Text)
    case_score: Mapped[int | None] = mapped_column(Integer)
    config_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("config_version.id"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("decision.id"))
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(  # Q20
        Uuid, ForeignKey("decision_proposal.id")
    )
    exception_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    exception_approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("staff_user.id")
    )


class DecisionApprover(Base):
    """One row per approver of a decision. Relational rather than a JSON list so
    dual control and recusal checks are plain joins."""

    __tablename__ = "decision_approver"
    __append_only__ = True

    decision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("decision.id"), index=True)
    approver_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("staff_user.id"), index=True)
    approver_role: Mapped[str] = mapped_column(Text)


class Appeal(Base):
    __tablename__ = "appeal"
    __append_only__ = True

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    decision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("decision.id"))
    eligibility_check_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("eligibility_check.id")
    )
    applicant_statement: Mapped[str] = mapped_column(Text)


class AppealDecision(Base):
    """The board's ruling on an appeal. Separate row because appeal is append-only."""

    __tablename__ = "appeal_decision"
    __append_only__ = True

    appeal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("appeal.id"), unique=True)
    outcome: Mapped[AppealOutcome] = mapped_column(str_enum(AppealOutcome, "appeal_outcome"))
    reasoning: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[list[str]] = mapped_column()  # staff_user ids (board members)
