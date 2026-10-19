from dataclasses import replace
from datetime import date

import pytest

from app.domain.approval import ApprovalState
from app.domain.caps import PriorGrant
from app.domain.config import Guideline
from app.domain.decisions import Proposal, check_proposal
from app.domain.enums import BalanceSource, Category, ConditionType, Tier
from app.domain.enums import DecisionOutcome as O
from app.domain.results import Reason
from tests.domain.helpers import cfg

C = cfg()
TODAY = date(2026, 10, 19)
A_FULL = Proposal(
    outcome=O.APPROVE_FULL,
    amount_requested=40_000,
    amount_approved=40_000,
    tier=Tier.A,
    category=Category.BABY,
    today=TODAY,
)


def violations(p: Proposal) -> list[str]:
    return [r.code for r in check_proposal(p, C).violations]


def test_clean_tier_a_approval() -> None:
    result = check_proposal(A_FULL, C)
    assert result.ok
    assert not result.exception_flag
    assert result.guideline is None


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"outcome": O.DECLINE, "amount_approved": 100}, "amount_must_be_zero_unless_approved"),
        ({"amount_approved": 0}, "approved_amount_must_be_positive"),
        ({"amount_approved": 50_000}, "amount_above_request"),
        ({"amount_approved": 30_000}, "full_approval_must_match_request"),
        ({"outcome": O.APPROVE_PARTIAL}, "partial_approval_must_be_below_request"),
        ({"outcome": O.APPROVE_CONDITIONAL}, "conditional_needs_condition_type"),
    ],
)
def test_amount_and_outcome_consistency(changes: dict[str, object], code: str) -> None:
    assert code in violations(replace(A_FULL, **changes))  # type: ignore[arg-type]


def test_decline_and_refer_with_zero_are_fine() -> None:
    assert violations(replace(A_FULL, outcome=O.DECLINE, amount_approved=0)) == []
    assert violations(replace(A_FULL, outcome=O.REFER, amount_approved=0)) == []


# --- AP-12 partial funding


PARTIAL = replace(A_FULL, outcome=O.APPROVE_PARTIAL, amount_approved=30_000)


@pytest.mark.parametrize("source", [None, BalanceSource.NONE])
def test_ap12_partial_without_balance_source_is_refused(source: BalanceSource | None) -> None:
    assert violations(replace(PARTIAL, balance_source=source)) == ["balance_source_required"]


def test_ap12_partial_with_balance_source() -> None:
    assert violations(replace(PARTIAL, balance_source=BalanceSource.FAMILY)) == []


def test_ap12_tier_c_needs_evidence() -> None:
    c_partial = replace(
        PARTIAL,
        tier=Tier.C,
        amount_requested=400_000,
        amount_approved=300_000,
        case_score=8,
        balance_source=BalanceSource.OTHER_ORG,
    )
    assert violations(c_partial) == ["balance_evidence_required"]
    assert violations(replace(c_partial, balance_evidence=True)) == []


def test_ap12_board_override_needs_reasoning() -> None:
    p = replace(PARTIAL, board_exception=True)
    assert violations(p) == ["exception_needs_reasoning"]
    ok = check_proposal(replace(p, reasoning="Landlord accepts partial"), C)
    assert ok.ok and ok.exception_flag
    assert [r.code for r in ok.exception_reasons] == ["balance_uncovered"]


# --- caps


CAP = (Reason("cap_household_amount", {"remaining": 10_000}),)


def test_caps_exceeded_needs_board() -> None:
    assert violations(replace(A_FULL, caps_exceeded=CAP)) == ["cap_household_amount"]
    ok = check_proposal(replace(A_FULL, caps_exceeded=CAP, board_exception=True, reasoning="x"), C)
    assert ok.ok and ok.exception_flag


def test_caps_do_not_matter_for_declines() -> None:
    assert (
        violations(replace(A_FULL, outcome=O.DECLINE, amount_approved=0, caps_exceeded=CAP)) == []
    )


# --- AP-9 repeat rent


def rent(paid: date | None) -> Proposal:
    prior = (PriorGrant(date(2026, 1, 1), 100_000, Category.RENT, paid),)
    return replace(A_FULL, category=Category.RENT, prior_grants=prior)


def test_ap9_repeat_rent_refuses_full_approval() -> None:
    assert violations(rent(date(2026, 1, 10))) == ["repeat_rent_requires_coaching"]


def test_ap9_conditional_coaching_is_accepted() -> None:
    p = replace(
        rent(date(2026, 1, 10)),
        outcome=O.APPROVE_CONDITIONAL,
        condition_type=ConditionType.COACHING_REFERRAL,
    )
    assert violations(p) == []
    wrong = replace(p, condition_type=ConditionType.CLAIM_ENTITLEMENT_FIRST)
    assert violations(wrong) == ["repeat_rent_requires_coaching"]


def test_ap9_board_exception() -> None:
    result = check_proposal(
        replace(rent(date(2026, 1, 10)), board_exception=True, reasoning="y"), C
    )
    assert result.ok
    assert result.exception_reasons[0].code == "repeat_rent_without_coaching"


@pytest.mark.parametrize(
    "paid",
    [None, date(2025, 10, 18)],  # never paid; paid outside the 365-day window
)
def test_ap9_not_a_repeat(paid: date | None) -> None:
    assert violations(rent(paid)) == []


def test_ap9_can_be_switched_off() -> None:
    c = cfg(**{"conditions.repeat_rent_requires_coaching": False})
    assert check_proposal(rent(date(2026, 1, 10)), c).ok


# --- guideline departures (scored tiers)


B = replace(A_FULL, tier=Tier.B, amount_requested=200_000, amount_approved=200_000)


def test_scored_tier_needs_a_case_score() -> None:
    assert violations(B) == ["case_score_required"]


def test_following_the_guideline() -> None:
    result = check_proposal(replace(B, case_score=10), C)
    assert result.ok and not result.exception_flag
    assert result.guideline is Guideline.APPROVE_FULL


def test_departure_needs_reasoning_and_sets_flag() -> None:
    assert violations(replace(B, case_score=4)) == ["exception_needs_reasoning"]
    result = check_proposal(replace(B, case_score=4, reasoning="Eviction next week"), C)
    assert result.ok and result.exception_flag
    assert result.exception_reasons[0].params == {"guideline": "refer_small_grant_with_reason"}


@pytest.mark.parametrize(
    ("state", "votes", "codes"),
    [
        (None, 0, []),
        (ApprovalState.PENDING, 0, []),  # unvoted proposal may be replaced
        (ApprovalState.REJECTED, 2, []),  # the panel agreed it was wrong
        (ApprovalState.PENDING, 1, ["proposal_already_voted"]),
        (ApprovalState.SPLIT, 2, ["proposal_already_voted"]),  # escalates instead
        (ApprovalState.CARRIED, 2, ["proposal_already_voted"]),
    ],
)
def test_q20_no_revote_on_different_terms(
    state: ApprovalState | None, votes: int, codes: list[str]
) -> None:
    from app.domain.decisions import check_new_proposal

    assert [r.code for r in check_new_proposal(state, votes)] == codes


# --- Q26 escalated tier A cases


@pytest.mark.parametrize(
    ("tier", "origin", "required"),
    [
        (Tier.A, None, False),
        (Tier.B, None, True),
        (Tier.B, Tier.A, False),  # decided on the tier A file as it is
        (Tier.C, Tier.A, False),  # still unscored after a further B -> C split
        (Tier.C, Tier.B, True),  # B cases were scored already
        (Tier.E, None, False),
    ],
)
def test_q26_scoring_required(tier: Tier, origin: Tier | None, required: bool) -> None:
    from app.domain.decisions import scoring_required

    assert scoring_required(tier, origin, C) is required


def test_q26_board_can_flip_scoring_for_escalated_tier_a() -> None:
    from app.domain.decisions import scoring_required

    flipped = cfg(**{"tiers.A.escalation_requires_scoring": True})
    assert scoring_required(Tier.B, Tier.A, flipped)


def test_q26_escalated_proposal_needs_no_score() -> None:
    escalated = replace(B, escalated_from=Tier.A)
    result = check_proposal(escalated, C)
    assert result.ok
    assert result.guideline is None


@pytest.mark.parametrize(
    ("origin", "made", "codes"),
    [
        (None, 5, []),  # not escalated: the tier's own document rules apply
        (Tier.A, 0, []),
        (Tier.A, 1, ["extra_request_limit"]),  # one extra document or phone check
        (Tier.B, 3, []),  # no limit configured for B
    ],
)
def test_q26_extra_requests(origin: Tier | None, made: int, codes: list[str]) -> None:
    from app.domain.decisions import check_extra_request

    assert [r.code for r in check_extra_request(origin, made, C)] == codes
