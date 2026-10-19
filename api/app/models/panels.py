"""Committee panels: alternates (Q21), proposals and per-member votes with
reasoning (Q20), amount amendments (Q21 boundary flag) and SLA clock events."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.config import Seat
from app.domain.enums import (
    BalanceSource,
    ConditionType,
    DecisionOutcome,
    RatificationOutcome,
    SlaEventKind,
    Tier,
)
from app.models._types import str_enum
from app.models.base import Base, MutableMixin


class CommitteeAlternate(MutableMixin, Base):
    """The board-approved alternates list. Board members may serve only by
    being on this list, never ad hoc."""

    __tablename__ = "committee_alternate"

    staff_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("staff_user.id"), unique=True)
    role: Mapped[str] = mapped_column(String(32))  # role held outside the committee
    approved_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("staff_user.id"))
    approved_at: Mapped[datetime]
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AlternateAssignment(Base):
    """An alternate seated on one case, with full member rights for that case
    only. The reason is internal and never shown to the applicant."""

    __tablename__ = "alternate_assignment"
    __append_only__ = True
    __table_args__ = (UniqueConstraint("case_id", "alternate_id", name="case_alternate"),)

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    alternate_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("committee_alternate.id"))
    assigner_role: Mapped[str] = mapped_column(String(32))  # committee_chair or board_chair
    reason: Mapped[str] = mapped_column(Text)


class DecisionProposal(Base):
    """What the panel votes on. When the vote carries, a Decision row is
    written from it. One proposal at a time; a voted proposal is never
    replaced (Q20)."""

    __tablename__ = "decision_proposal"
    __append_only__ = True
    __table_args__ = (CheckConstraint("amount_approved >= 0", name="amount_non_negative"),)

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    tier: Mapped[Tier] = mapped_column(str_enum(Tier, "tier"))
    outcome: Mapped[DecisionOutcome] = mapped_column(str_enum(DecisionOutcome, "outcome"))
    amount_approved: Mapped[int] = mapped_column(BigInteger)  # agorot
    conditions: Mapped[str | None] = mapped_column(Text)
    condition_type: Mapped[ConditionType | None] = mapped_column(
        str_enum(ConditionType, "condition_type")
    )
    balance_source: Mapped[BalanceSource | None] = mapped_column(
        str_enum(BalanceSource, "balance_source")
    )
    balance_evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document.id")
    )
    reasoning: Mapped[str] = mapped_column(Text, default="")
    config_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("config_version.id"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("decision_proposal.id")
    )


class DecisionVote(Base):
    """Each member's vote with one line of reasoning, dissent included.
    Matters for appeals."""

    __tablename__ = "decision_vote"
    __append_only__ = True
    __table_args__ = (
        UniqueConstraint("proposal_id", "voter_id", name="one_vote_each"),
        CheckConstraint("length(trim(reasoning)) > 0", name="reasoning_required"),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("decision_proposal.id"), index=True
    )
    voter_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("staff_user.id"))
    seat: Mapped[Seat] = mapped_column(str_enum(Seat, "seat"))
    in_favour: Mapped[bool] = mapped_column(Boolean)
    reasoning: Mapped[str] = mapped_column(String(500))
    alternate_assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("alternate_assignment.id")
    )


class AmountAmendment(Base):
    """A requested amount re-entered after submission. The applicant may lower
    a request; staff never suggest it. Amounts near a tier boundary are
    flagged for the audit committee (Q21)."""

    __tablename__ = "amount_amendment"
    __append_only__ = True
    __table_args__ = (CheckConstraint("new_amount > 0", name="amount_positive"),)

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    previous_amount: Mapped[int] = mapped_column(BigInteger)
    new_amount: Mapped[int] = mapped_column(BigInteger)
    by_applicant: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)
    near_boundary: Mapped[bool] = mapped_column(Boolean, index=True)
    boundary: Mapped[int | None] = mapped_column(BigInteger)


class SlaEventRow(Base):
    """SLA clock pauses (no alternate available), resumptions, and restarts
    (escalation to a larger panel)."""

    __tablename__ = "sla_event"
    __append_only__ = True

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    kind: Mapped[SlaEventKind] = mapped_column(str_enum(SlaEventKind, "sla_event_kind"))
    tier: Mapped[Tier | None] = mapped_column(str_enum(Tier, "tier"))
    reason: Mapped[str] = mapped_column(Text)


class Ratification(Base):
    """Q23: the full committee ratifies or overturns an emergency decision at
    its next meeting. Overturned after payment: noted here, no clawback, and
    the grant still counts against the household's caps."""

    __tablename__ = "ratification"
    __append_only__ = True

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    decision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("decision.id"), unique=True)
    outcome: Mapped[RatificationOutcome] = mapped_column(
        str_enum(RatificationOutcome, "ratification_outcome")
    )
    reasoning: Mapped[str] = mapped_column(Text)
    meeting_reference: Mapped[str] = mapped_column(String(128))
