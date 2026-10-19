from dataclasses import replace

import pytest

from app.domain.approval import ApprovalState
from app.domain.documents import Requirement
from app.domain.enums import CaseStatus as S
from app.domain.enums import DocumentType, Tier
from app.domain.workflow import (
    APPEALABLE,
    TERMINAL,
    TRANSITIONS,
    IllegalTransition,
    TransitionContext,
    allowed_targets,
    check_transition,
    transition,
)
from tests.domain.helpers import cfg

C = cfg()
CTX = TransitionContext(reason="coordinator note")
MISSING = (Requirement((DocumentType.LEASE,)),)


def refused(frm: S, to: S, ctx: TransitionContext = CTX) -> list[str]:
    return [r.code for r in check_transition(frm, to, ctx, C)]


def test_every_status_is_reachable_and_terminals_have_no_exit_except_appeal() -> None:
    targets = {to for (_, to) in TRANSITIONS}
    assert set(S) - targets == {S.SUBMITTED}
    for status in TERMINAL - APPEALABLE:
        assert allowed_targets(status) == frozenset()
    for status in APPEALABLE:
        assert allowed_targets(status) == {S.UNDER_APPEAL}


def test_illegal_transition_raises_with_reasons() -> None:
    with pytest.raises(IllegalTransition, match="illegal_transition") as exc:
        transition(S.SUBMITTED, S.PAID, CTX, C)
    assert exc.value.reasons[0].params == {"from": "submitted", "to": "paid"}


def test_every_transition_needs_a_reason() -> None:
    assert refused(S.SUBMITTED, S.INTAKE_REVIEW, replace(CTX, reason="  ")) == ["reason_required"]
    assert transition(S.SUBMITTED, S.INTAKE_REVIEW, CTX, C) is S.INTAKE_REVIEW


@pytest.mark.parametrize(
    ("to", "gate", "codes"),
    [
        (S.ELIGIBLE, True, []),
        (S.ELIGIBLE, False, ["gate_not_passed"]),
        (S.ELIGIBLE, None, ["gate_not_passed"]),
        (S.INELIGIBLE, False, []),
        (S.INELIGIBLE, True, ["gate_not_failed"]),
    ],
)
def test_intake_review_follows_the_gate(to: S, gate: bool | None, codes: list[str]) -> None:
    assert refused(S.INTAKE_REVIEW, to, replace(CTX, gate_passed=gate)) == codes


@pytest.mark.parametrize(
    ("tier", "call", "codes"),
    [
        (Tier.A, False, []),
        (Tier.B, False, ["intake_call_required"]),
        (Tier.C, False, ["intake_call_required"]),
        (Tier.B, True, []),
    ],
)
def test_ap5_intake_call_before_documents(tier: Tier, call: bool, codes: list[str]) -> None:
    ctx = replace(CTX, tier=tier, intake_call_proceed=call)
    assert refused(S.ELIGIBLE, S.AWAITING_DOCUMENTS, ctx) == codes


def test_tier_must_be_known() -> None:
    with pytest.raises(ValueError, match="tier"):
        check_transition(S.ELIGIBLE, S.AWAITING_DOCUMENTS, CTX, C)


@pytest.mark.parametrize(
    ("tier", "missing", "rights", "codes"),
    [
        (Tier.B, (), True, []),
        (Tier.B, MISSING, True, ["documents_missing"]),
        (Tier.B, (), False, ["rights_check_required"]),  # AP-7
        (Tier.A, (), True, ["tier_not_scored"]),
    ],
)
def test_into_scoring(
    tier: Tier, missing: tuple[Requirement, ...], rights: bool, codes: list[str]
) -> None:
    ctx = replace(CTX, tier=tier, documents_missing=missing, rights_check_done=rights)
    assert refused(S.VERIFICATION, S.SCORING, ctx) == codes


def test_missing_documents_are_listed() -> None:
    ctx = replace(CTX, tier=Tier.B, documents_missing=MISSING, rights_check_done=True)
    reason = check_transition(S.VERIFICATION, S.SCORING, ctx, C)[0]
    assert reason.params == {"missing": [["lease"]]}


@pytest.mark.parametrize(
    ("tier", "missing", "codes"),
    [
        (Tier.A, (), []),  # tier A skips scoring (D15)
        (Tier.A, MISSING, ["documents_missing"]),
        (Tier.B, (), ["tier_requires_scoring"]),
    ],
)
def test_tier_a_goes_straight_to_decision(
    tier: Tier, missing: tuple[Requirement, ...], codes: list[str]
) -> None:
    ctx = replace(CTX, tier=tier, documents_missing=missing)
    assert refused(S.VERIFICATION, S.DECISION_PENDING, ctx) == codes


@pytest.mark.parametrize(
    ("tier", "have", "ok"), [(Tier.B, 2, True), (Tier.B, 1, False), (Tier.C, 2, False)]
)
def test_scoring_needs_every_seat(tier: Tier, have: int, ok: bool) -> None:
    codes = refused(S.SCORING, S.DECISION_PENDING, replace(CTX, tier=tier, scores_submitted=have))
    assert codes == ([] if ok else ["scores_incomplete"])


@pytest.mark.parametrize("to", [S.APPROVED, S.PARTIAL, S.CONDITIONAL, S.REFERRED, S.DECLINED])
@pytest.mark.parametrize(
    "state",
    [
        ApprovalState.CARRIED,
        ApprovalState.PENDING,
        ApprovalState.REJECTED,
        ApprovalState.SPLIT,
        None,
    ],
)
def test_decisions_need_a_carried_vote(to: S, state: ApprovalState | None) -> None:
    codes = refused(S.DECISION_PENDING, to, replace(CTX, approval=state))
    assert codes == ([] if state is ApprovalState.CARRIED else ["decision_not_carried"])


def test_emergency_path() -> None:
    carried = replace(CTX, tier=Tier.E, approval=ApprovalState.CARRIED)
    assert refused(S.EMERGENCY_REVIEW, S.APPROVED, carried) == []
    assert refused(S.EMERGENCY_REVIEW, S.APPROVED, replace(carried, tier=Tier.B)) == [
        "not_emergency_tier"
    ]
    # Emergency grants are paid first and ratified before follow-up.
    assert refused(S.PAID, S.FOLLOW_UP, carried) == ["ratification_first"]
    assert refused(S.PAID, S.RATIFICATION_PENDING, carried) == []
    assert refused(S.RATIFICATION_PENDING, S.FOLLOW_UP, carried) == ["ratification_not_recorded"]
    # Ratified or overturned, the case moves on; an overturned paid grant is not clawed back.
    recorded = replace(carried, ratification_recorded=True)
    assert refused(S.RATIFICATION_PENDING, S.FOLLOW_UP, recorded) == []


def test_non_emergency_payment_goes_to_follow_up() -> None:
    ctx = replace(CTX, tier=Tier.B)
    assert refused(S.PAID, S.FOLLOW_UP, ctx) == []
    assert refused(S.PAID, S.RATIFICATION_PENDING, ctx) == ["tier_not_ratified"]


def test_ap16_case_cannot_close_without_follow_up() -> None:
    assert refused(S.FOLLOW_UP, S.CLOSED) == ["follow_up_required"]
    assert refused(S.FOLLOW_UP, S.CLOSED, replace(CTX, follow_up_recorded=True)) == []


@pytest.mark.parametrize(
    ("original", "back_to", "codes"),
    [
        (S.DECLINED, S.DECLINED, []),
        (S.DECLINED, S.INELIGIBLE, ["appeal_returns_to_original_status"]),
        (S.INELIGIBLE, S.INELIGIBLE, []),
        (S.INELIGIBLE, S.DECISION_PENDING, []),
    ],
)
def test_appeals(original: S, back_to: S, codes: list[str]) -> None:
    assert refused(S.UNDER_APPEAL, back_to, replace(CTX, appealed_from=original)) == codes


@pytest.mark.parametrize("frm", [S.SUBMITTED, S.SCORING, S.DECISION_PENDING])
def test_withdrawal_before_decision(frm: S) -> None:
    assert refused(frm, S.WITHDRAWN) == []


def test_no_withdrawal_after_approval() -> None:
    assert refused(S.APPROVED, S.WITHDRAWN) == ["illegal_transition"]


def test_payment_path() -> None:
    for frm, to in [
        (S.APPROVED, S.PAYMENT_APPROVED),
        (S.PAYMENT_APPROVED, S.IN_BATCH),
        (S.IN_BATCH, S.PAID),
        (S.IN_BATCH, S.PAYMENT_APPROVED),
    ]:
        assert refused(frm, to) == []
