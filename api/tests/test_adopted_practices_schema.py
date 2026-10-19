"""Database-level guarantees for ADOPTED_PRACTICES items. Behavioural tests
for each AP item arrive with the phase that implements it."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums import (
    AllocationStatus,
    Category,
    DecisionOutcome,
    IntakeCallOutcome,
    LeadStatus,
    PaymentMethod,
    ReferrerStatus,
)
from app.models import (
    AidCase,
    Allocation,
    Decision,
    DecisionProposal,
    IntakeCall,
    Lead,
    Payment,
    Referrer,
)
from tests import factories


def test_ap1_new_referrers_start_pending(session: Session) -> None:
    r = Referrer(name="Synthetic", role="social worker", organisation="Synthetic dept")
    session.add(r)
    session.flush()
    assert r.status is ReferrerStatus.PENDING


def test_ap3_case_from_lead_requires_consent(session: Session) -> None:
    cfg = factories.config(session)
    c = factories.case(session, cfg)
    lead = Lead(subject_name="Synthetic", status=LeadStatus.CONTACTED)
    session.add(lead)
    session.commit()
    with pytest.raises(IntegrityError):
        session.execute(update(Lead).where(Lead.id == lead.id).values(converted_case_id=c.id))
        session.flush()
    session.rollback()
    session.execute(
        update(Lead)
        .where(Lead.id == lead.id)
        .values(consented_at=datetime.now(UTC), converted_case_id=c.id)
    )
    session.commit()


def test_ap5_intake_calls_are_append_only(session: Session) -> None:
    cfg = factories.config(session)
    c = factories.case(session, cfg)
    call = IntakeCall(
        case_id=c.id,
        called_at=datetime.now(UTC),
        duration_minutes=12,
        summary="synthetic",
        outcome=IntakeCallOutcome.PROCEED,
    )
    session.add(call)
    session.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(update(IntakeCall).values(outcome=IntakeCallOutcome.WITHDRAWN))
    session.rollback()


def _allocation(session: Session) -> tuple[Allocation, Decision]:
    cfg = factories.config(session)
    c = factories.case(session, cfg)
    d = Decision(
        case_id=c.id,
        outcome=DecisionOutcome.APPROVE_FULL,
        amount_approved=60_000,
        config_version_id=cfg.id,
    )
    session.add(d)
    session.flush()
    from app.models import Applicant

    applicant = session.get(Applicant, c.applicant_id)
    assert applicant is not None
    a = Allocation(
        case_id=c.id,
        decision_id=d.id,
        household_id=applicant.household_id,
        child_birth_month=date(2026, 5, 1),
        category=Category.BABY,
        monthly_amount=5_000,
        method=PaymentMethod.VOUCHER,
        start_month=date(2026, 6, 1),
        end_month=date(2027, 5, 1),
        config_version_id=cfg.id,
        status=AllocationStatus.ACTIVE,
    )
    session.add(a)
    session.flush()
    return a, d


def test_ap15_one_payment_per_allocation_month(session: Session) -> None:
    a, d = _allocation(session)

    def pay(month: date) -> Payment:
        return Payment(
            decision_id=d.id,
            vendor="Synthetic chain",
            amount=5_000,
            method=PaymentMethod.VOUCHER,
            allocation_id=a.id,
            allocation_month=month,
        )

    session.add(pay(date(2026, 6, 1)))
    session.add(pay(date(2026, 7, 1)))
    session.commit()
    session.add(pay(date(2026, 6, 1)))
    with pytest.raises(IntegrityError):
        session.flush()


def test_ap15_allocation_months_must_be_ordered(session: Session) -> None:
    a, _ = _allocation(session)
    session.commit()
    with pytest.raises(IntegrityError):
        session.execute(
            update(Allocation).where(Allocation.id == a.id).values(end_month=date(2026, 1, 1))
        )


# --- Q20 votes and Q21 alternates at the database level


def _proposal(session: Session) -> tuple[AidCase, DecisionProposal]:
    from app.domain.enums import Tier

    cfg = factories.config(session)
    c = factories.case(session, cfg)
    p = DecisionProposal(
        case_id=c.id,
        tier=Tier.B,
        outcome=DecisionOutcome.APPROVE_FULL,
        amount_approved=120_000,
        config_version_id=cfg.id,
    )
    session.add(p)
    session.flush()
    return c, p


def test_q20_one_vote_per_member_per_proposal(session: Session) -> None:
    from app.domain.config import Seat
    from app.domain.enums import Role
    from app.models import DecisionVote

    _, p = _proposal(session)
    member = factories.staff(session, Role.COMMITTEE_MEMBER)
    session.add(
        DecisionVote(
            proposal_id=p.id,
            voter_id=member.id,
            seat=Seat.COMMITTEE,
            in_favour=True,
            reasoning="Clear need",
        )
    )
    session.commit()
    session.add(
        DecisionVote(
            proposal_id=p.id,
            voter_id=member.id,
            seat=Seat.COMMITTEE,
            in_favour=False,
            reasoning="Changed my mind",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_q20_vote_needs_reasoning_and_is_append_only(session: Session) -> None:
    from app.domain.config import Seat
    from app.domain.enums import Role
    from app.models import DecisionVote

    _, p = _proposal(session)
    member = factories.staff(session, Role.COMMITTEE_MEMBER)
    session.add(
        DecisionVote(
            proposal_id=p.id,
            voter_id=member.id,
            seat=Seat.COMMITTEE,
            in_favour=False,
            reasoning="   ",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    _, p = _proposal(session)
    member = factories.staff(session, Role.COMMITTEE_MEMBER, email="m2@test.invalid")
    session.add(
        DecisionVote(
            proposal_id=p.id,
            voter_id=member.id,
            seat=Seat.COMMITTEE,
            in_favour=False,
            reasoning="Dissent",
        )
    )
    session.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(update(DecisionVote).values(in_favour=True))


def test_q20_escalation_flag_is_a_workflow_column(session: Session) -> None:
    from app.domain.enums import Tier

    cfg = factories.config(session)
    c = factories.case(session, cfg)
    session.commit()
    session.execute(
        update(AidCase).where(AidCase.id == c.id).values(tier=Tier.C, escalated_from_tier=Tier.B)
    )
    session.commit()


def test_q25_band_is_never_e(session: Session) -> None:
    from app.domain.enums import Tier
    from app.models import TierAssignment

    cfg = factories.config(session)
    c = factories.case(session, cfg)

    def row(band: Tier) -> TierAssignment:
        return TierAssignment(
            case_id=c.id,
            tier=Tier.E,
            band=band,
            amount=150_000,
            payment_periods=1,
            emergency=True,
            config_version_id=cfg.id,
        )

    session.add(row(Tier.B))
    session.flush()
    session.add(row(Tier.E))
    with pytest.raises(IntegrityError):
        session.flush()
