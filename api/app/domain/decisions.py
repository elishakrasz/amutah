"""Checks on a proposed decision before it is put to a vote. The engine lists
violations and flags exceptions; people decide (D24)."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.domain.approval import ApprovalState
from app.domain.caps import PriorGrant
from app.domain.config import Guideline, RulesConfig
from app.domain.enums import BalanceSource, Category, ConditionType, DecisionOutcome, Tier
from app.domain.results import Reason
from app.domain.scoring import departs_from_guideline, guideline

APPROVALS = frozenset(
    {
        DecisionOutcome.APPROVE_FULL,
        DecisionOutcome.APPROVE_PARTIAL,
        DecisionOutcome.APPROVE_CONDITIONAL,
    }
)


@dataclass(frozen=True)
class Proposal:
    outcome: DecisionOutcome
    amount_requested: int
    amount_approved: int
    tier: Tier
    category: Category
    today: date
    case_score: int | None = None  # tiers that require scoring
    reasoning: str = ""
    condition_type: ConditionType | None = None
    balance_source: BalanceSource | None = None
    balance_evidence: bool = False
    caps_exceeded: tuple[Reason, ...] = ()
    prior_grants: tuple[PriorGrant, ...] = field(default=())
    board_exception: bool = False
    escalated_from: Tier | None = None  # the tier the case started at (Q26)


@dataclass(frozen=True)
class ProposalCheck:
    violations: tuple[Reason, ...]
    exception_flag: bool
    exception_reasons: tuple[Reason, ...]
    guideline: Guideline | None

    @property
    def ok(self) -> bool:
        return not self.violations


def _repeat_rent(p: Proposal, cfg: RulesConfig) -> bool:
    if p.category is not Category.RENT or not cfg.conditions.repeat_rent_requires_coaching:
        return False
    since = p.today - timedelta(days=cfg.conditions.repeat_window_days)
    return any(
        g.category is Category.RENT and g.paid_on is not None and g.paid_on >= since
        for g in p.prior_grants
    )


def check_proposal(p: Proposal, cfg: RulesConfig) -> ProposalCheck:
    violations: list[Reason] = []
    exceptions: list[Reason] = []
    approving = p.outcome in APPROVALS

    # Amount consistency
    if not approving and p.amount_approved != 0:
        violations.append(Reason("amount_must_be_zero_unless_approved"))
    if approving and p.amount_approved <= 0:
        violations.append(Reason("approved_amount_must_be_positive"))
    if p.amount_approved > p.amount_requested:
        violations.append(Reason("amount_above_request"))
    if p.outcome is DecisionOutcome.APPROVE_FULL and p.amount_approved != p.amount_requested:
        violations.append(Reason("full_approval_must_match_request"))
    if p.outcome is DecisionOutcome.APPROVE_PARTIAL and p.amount_approved >= p.amount_requested:
        violations.append(Reason("partial_approval_must_be_below_request"))
    if p.outcome is DecisionOutcome.APPROVE_CONDITIONAL and p.condition_type is None:
        violations.append(Reason("conditional_needs_condition_type"))

    # AP-12: the unfunded remainder must be covered.
    if approving and 0 < p.amount_approved < p.amount_requested:
        if p.balance_source in (None, BalanceSource.NONE):
            if p.board_exception:
                exceptions.append(Reason("balance_uncovered"))
            else:
                violations.append(Reason("balance_source_required"))
        elif p.tier is Tier.C and not p.balance_evidence:
            violations.append(Reason("balance_evidence_required"))

    # Caps
    if approving and p.caps_exceeded:
        if p.board_exception:
            exceptions.extend(p.caps_exceeded)
        else:
            violations.extend(p.caps_exceeded)

    # AP-9: repeat rent help comes with a coaching referral.
    if approving and _repeat_rent(p, cfg):
        coached = (
            p.outcome is DecisionOutcome.APPROVE_CONDITIONAL
            and p.condition_type is ConditionType.COACHING_REFERRAL
        )
        if not coached:
            if p.board_exception:
                exceptions.append(Reason("repeat_rent_without_coaching"))
            else:
                violations.append(
                    Reason(
                        "repeat_rent_requires_coaching",
                        {"organisation": cfg.conditions.coaching_default_org},
                    )
                )

    # Guideline departure (scored tiers)
    g = None
    if scoring_required(p.tier, p.escalated_from, cfg):
        if p.case_score is None:
            violations.append(Reason("case_score_required"))
        else:
            g = guideline(p.case_score, cfg)
            if departs_from_guideline(p.outcome, g):
                exceptions.append(Reason("departs_from_guideline", {"guideline": g.value}))

    if exceptions and not p.reasoning.strip():
        violations.append(Reason("exception_needs_reasoning"))

    return ProposalCheck(
        violations=tuple(violations),
        exception_flag=bool(exceptions),
        exception_reasons=tuple(exceptions),
        guideline=g,
    )


def scoring_required(tier: Tier, escalated_from: Tier | None, cfg: RulesConfig) -> bool:
    """Q26: a case escalated from an unscored tier is decided on the file as
    it is, at every higher tier, unless the board flips
    escalation_requires_scoring for the starting tier."""
    if not cfg.tier(tier).requires_scoring:
        return False
    if escalated_from is None:
        return True
    origin = cfg.tier(escalated_from)
    return origin.requires_scoring or origin.escalation_requires_scoring


def check_extra_request(
    escalated_from: Tier | None, requests_made: int, cfg: RulesConfig
) -> tuple[Reason, ...]:
    """Q26: an escalated panel may ask for at most N extra items (one
    document or one phone verification), never the higher tier's full set."""
    if escalated_from is None:
        return ()
    limit = cfg.tier(escalated_from).escalation_extra_requests
    if limit is not None and requests_made >= limit:
        return (Reason("extra_request_limit", {"limit": limit}),)
    return ()


def check_new_proposal(active_state: ApprovalState | None, votes_cast: int) -> tuple[Reason, ...]:
    """One proposal at a time (Q20). A new one may be tabled when there is
    none, the current one has no votes yet, or the panel rejected it. A
    voted, undecided or split proposal stands: no re-vote on different terms."""
    if active_state is None or active_state is ApprovalState.REJECTED or votes_cast == 0:
        return ()
    return (Reason("proposal_already_voted"),)
