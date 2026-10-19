"""Committee scoring (tiers B and C), guideline bands, and the suggested
scores from the rights check (AP-7) shown beside the rubric."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.config import Guideline, MedianRounding, RulesConfig
from app.domain.enums import DecisionOutcome, RightsStatus
from app.domain.results import Reason, Suggestion

DIMENSION_MAX = {"need": 3, "urgency": 3, "impact": 3, "alternatives": 3, "vulnerability": 1}

GUIDELINE_OUTCOMES: dict[Guideline, frozenset[DecisionOutcome]] = {
    Guideline.APPROVE_FULL: frozenset({DecisionOutcome.APPROVE_FULL}),
    Guideline.PARTIAL_OR_CONDITIONAL: frozenset(
        {DecisionOutcome.APPROVE_PARTIAL, DecisionOutcome.APPROVE_CONDITIONAL}
    ),
    # "refer; small grant only with written reason": a grant here is a departure.
    Guideline.REFER: frozenset({DecisionOutcome.REFER}),
    Guideline.DECLINE: frozenset({DecisionOutcome.DECLINE}),
}


@dataclass(frozen=True)
class ScoreCard:
    need: int
    urgency: int
    impact: int
    alternatives: int
    vulnerability: int

    def __post_init__(self) -> None:
        for name, top in DIMENSION_MAX.items():
            value = getattr(self, name)
            if not 0 <= value <= top:
                raise ValueError(f"{name} must be between 0 and {top}")

    @property
    def total(self) -> int:
        return self.need + self.urgency + self.impact + self.alternatives + self.vulnerability


def case_score(totals: Sequence[int], cfg: RulesConfig) -> int:
    """Median of the members' totals. An even count averages the middle two;
    a .5 result rounds per config (the board chose up)."""
    if not totals:
        raise ValueError("no scores submitted")
    ordered = sorted(totals)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    pair = ordered[mid - 1] + ordered[mid]
    return (pair + 1) // 2 if cfg.median_rounding is MedianRounding.UP else pair // 2


def guideline(score: int, cfg: RulesConfig) -> Guideline:
    for band in cfg.score_bands:
        if band.min <= score <= band.max:
            return band.guideline
    raise ValueError(f"score {score} is outside 0..{cfg.max_score}")


def departs_from_guideline(outcome: DecisionOutcome, g: Guideline) -> bool:
    return outcome not in GUIDELINE_OUTCOMES[g]


def suggest_alternatives(statuses: Sequence[RightsStatus], cfg: RulesConfig) -> Suggestion:
    """AP-7: any unclaimed entitlement means the applicant has alternatives."""
    rules = cfg.rights
    unclaimed = sum(1 for s in statuses if s is RightsStatus.ELIGIBLE_NOT_CLAIMED)
    if unclaimed:
        r = rules.eligible_not_claimed
        return Suggestion(r.low, r.high, Reason("rights_unclaimed", {"count": unclaimed}))
    in_progress = sum(1 for s in statuses if s is RightsStatus.CLAIM_IN_PROGRESS)
    if in_progress:
        r = rules.claim_in_progress
        return Suggestion(r.low, r.high, Reason("rights_in_progress", {"count": in_progress}))
    r = rules.resolved
    return Suggestion(r.low, r.high, Reason("rights_resolved"))
