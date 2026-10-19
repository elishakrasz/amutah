"""The case status machine: every legal transition and its guard, in one
table. Illegal transitions raise. The service writes a case_transition row
and an audit event for every transition that passes."""

from collections.abc import Callable
from dataclasses import dataclass

from app.domain.approval import ApprovalState
from app.domain.config import RulesConfig
from app.domain.documents import Requirement
from app.domain.enums import CaseStatus as S
from app.domain.enums import Tier
from app.domain.results import Reason

TERMINAL = frozenset({S.INELIGIBLE, S.REFERRED, S.DECLINED, S.CLOSED, S.WITHDRAWN})
APPEALABLE = frozenset({S.INELIGIBLE, S.DECLINED})
WITHDRAWABLE = frozenset(
    {
        S.SUBMITTED,
        S.EMERGENCY_REVIEW,
        S.INTAKE_REVIEW,
        S.ELIGIBLE,
        S.AWAITING_DOCUMENTS,
        S.VERIFICATION,
        S.SCORING,
        S.DECISION_PENDING,
    }
)


class IllegalTransition(Exception):
    def __init__(self, reasons: tuple[Reason, ...]) -> None:
        super().__init__(", ".join(r.code for r in reasons))
        self.reasons = reasons


@dataclass(frozen=True)
class TransitionContext:
    reason: str  # the person's stated reason; always required
    tier: Tier | None = None
    gate_passed: bool | None = None
    intake_call_proceed: bool = False  # AP-5
    rights_check_done: bool = False  # AP-7
    documents_missing: tuple[Requirement, ...] = ()
    scores_submitted: int = 0
    approval: ApprovalState | None = None
    appealed_from: S | None = None
    follow_up_recorded: bool = False  # AP-16
    ratification_recorded: bool = False  # ratified or overturned (Q23)


Guard = Callable[[TransitionContext, RulesConfig], tuple[Reason, ...]]


def _ok(*_: object) -> tuple[Reason, ...]:
    return ()


def _tier_set(ctx: TransitionContext) -> Tier:
    if ctx.tier is None:
        raise ValueError("tier must be assigned before this transition")
    return ctx.tier


def _gate_passed(ctx: TransitionContext, _: RulesConfig) -> tuple[Reason, ...]:
    return () if ctx.gate_passed is True else (Reason("gate_not_passed"),)


def _gate_failed(ctx: TransitionContext, _: RulesConfig) -> tuple[Reason, ...]:
    return () if ctx.gate_passed is False else (Reason("gate_not_failed"),)


def _intake_call(ctx: TransitionContext, cfg: RulesConfig) -> tuple[Reason, ...]:
    needed = cfg.tier(_tier_set(ctx)).requires_intake_call
    return (Reason("intake_call_required"),) if needed and not ctx.intake_call_proceed else ()


def _documents(ctx: TransitionContext) -> tuple[Reason, ...]:
    if not ctx.documents_missing:
        return ()
    missing = [sorted(d.value for d in r.any_of) for r in ctx.documents_missing]
    return (Reason("documents_missing", {"missing": missing}),)


def _to_scoring(ctx: TransitionContext, cfg: RulesConfig) -> tuple[Reason, ...]:
    out = list(_documents(ctx))
    if not cfg.tier(_tier_set(ctx)).requires_scoring:
        out.append(Reason("tier_not_scored"))
    if not ctx.rights_check_done:
        out.append(Reason("rights_check_required"))
    return tuple(out)


def _verification_to_decision(ctx: TransitionContext, cfg: RulesConfig) -> tuple[Reason, ...]:
    out = list(_documents(ctx))
    if cfg.tier(_tier_set(ctx)).requires_scoring:
        out.append(Reason("tier_requires_scoring"))
    return tuple(out)


def _scores_complete(ctx: TransitionContext, cfg: RulesConfig) -> tuple[Reason, ...]:
    needed = cfg.tier(_tier_set(ctx)).approval.total_seats
    if ctx.scores_submitted < needed:
        return (Reason("scores_incomplete", {"needed": needed, "have": ctx.scores_submitted}),)
    return ()


def _carried(ctx: TransitionContext, _: RulesConfig) -> tuple[Reason, ...]:
    return () if ctx.approval is ApprovalState.CARRIED else (Reason("decision_not_carried"),)


def _emergency_carried(ctx: TransitionContext, cfg: RulesConfig) -> tuple[Reason, ...]:
    out = list(_carried(ctx, cfg))
    if _tier_set(ctx) is not Tier.E:
        out.append(Reason("not_emergency_tier"))
    return tuple(out)


def _paid_to_follow_up(ctx: TransitionContext, cfg: RulesConfig) -> tuple[Reason, ...]:
    if cfg.tier(_tier_set(ctx)).requires_ratification:
        return (Reason("ratification_first"),)
    return ()


def _paid_to_ratification(ctx: TransitionContext, cfg: RulesConfig) -> tuple[Reason, ...]:
    if not cfg.tier(_tier_set(ctx)).requires_ratification:
        return (Reason("tier_not_ratified"),)
    return ()


def _ratified(ctx: TransitionContext, _: RulesConfig) -> tuple[Reason, ...]:
    """Either outcome moves on. An overturned grant that was already paid
    is not clawed back; it still counts against the household's caps."""
    return () if ctx.ratification_recorded else (Reason("ratification_not_recorded"),)


def _follow_up(ctx: TransitionContext, _: RulesConfig) -> tuple[Reason, ...]:
    return () if ctx.follow_up_recorded else (Reason("follow_up_required"),)


def _appeal_upheld(original: S) -> Guard:
    def guard(ctx: TransitionContext, _: RulesConfig) -> tuple[Reason, ...]:
        if ctx.appealed_from is not original:
            return (Reason("appeal_returns_to_original_status"),)
        return ()

    return guard


TRANSITIONS: dict[tuple[S, S], Guard] = {
    (S.SUBMITTED, S.INTAKE_REVIEW): _ok,
    (S.SUBMITTED, S.EMERGENCY_REVIEW): _ok,
    (S.EMERGENCY_REVIEW, S.APPROVED): _emergency_carried,
    (S.EMERGENCY_REVIEW, S.INTAKE_REVIEW): _ok,  # chair declines the emergency path
    (S.INTAKE_REVIEW, S.ELIGIBLE): _gate_passed,
    (S.INTAKE_REVIEW, S.INELIGIBLE): _gate_failed,
    (S.ELIGIBLE, S.AWAITING_DOCUMENTS): _intake_call,
    (S.ELIGIBLE, S.REFERRED): _ok,  # intake call outcome refer_elsewhere
    (S.AWAITING_DOCUMENTS, S.VERIFICATION): _ok,
    (S.VERIFICATION, S.AWAITING_DOCUMENTS): _ok,
    (S.VERIFICATION, S.SCORING): _to_scoring,
    (S.VERIFICATION, S.DECISION_PENDING): _verification_to_decision,
    (S.SCORING, S.DECISION_PENDING): _scores_complete,
    (S.DECISION_PENDING, S.APPROVED): _carried,
    (S.DECISION_PENDING, S.PARTIAL): _carried,
    (S.DECISION_PENDING, S.CONDITIONAL): _carried,
    (S.DECISION_PENDING, S.REFERRED): _carried,
    (S.DECISION_PENDING, S.DECLINED): _carried,
    (S.APPROVED, S.PAYMENT_APPROVED): _ok,
    (S.PARTIAL, S.PAYMENT_APPROVED): _ok,
    (S.CONDITIONAL, S.PAYMENT_APPROVED): _ok,
    (S.PAYMENT_APPROVED, S.IN_BATCH): _ok,
    (S.IN_BATCH, S.PAID): _ok,
    (S.IN_BATCH, S.PAYMENT_APPROVED): _ok,  # bank rejected the transfer
    (S.PAID, S.FOLLOW_UP): _paid_to_follow_up,
    (S.PAID, S.RATIFICATION_PENDING): _paid_to_ratification,
    (S.RATIFICATION_PENDING, S.FOLLOW_UP): _ratified,
    (S.FOLLOW_UP, S.CLOSED): _follow_up,
    (S.INELIGIBLE, S.UNDER_APPEAL): _ok,
    (S.DECLINED, S.UNDER_APPEAL): _ok,
    (S.UNDER_APPEAL, S.DECISION_PENDING): _ok,
    (S.UNDER_APPEAL, S.INELIGIBLE): _appeal_upheld(S.INELIGIBLE),
    (S.UNDER_APPEAL, S.DECLINED): _appeal_upheld(S.DECLINED),
    **{(s, S.WITHDRAWN): _ok for s in WITHDRAWABLE},
}


def allowed_targets(current: S) -> frozenset[S]:
    return frozenset(to for (frm, to) in TRANSITIONS if frm is current)


def check_transition(
    current: S, target: S, ctx: TransitionContext, cfg: RulesConfig
) -> tuple[Reason, ...]:
    """Reasons the transition is refused; empty means it may proceed."""
    guard = TRANSITIONS.get((current, target))
    if guard is None:
        return (Reason("illegal_transition", {"from": current.value, "to": target.value}),)
    reasons = list(guard(ctx, cfg))
    if not ctx.reason.strip():
        reasons.append(Reason("reason_required"))
    return tuple(reasons)


def transition(current: S, target: S, ctx: TransitionContext, cfg: RulesConfig) -> S:
    reasons = check_transition(current, target, ctx, cfg)
    if reasons:
        raise IllegalTransition(reasons)
    return target
