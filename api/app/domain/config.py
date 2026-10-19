"""Typed, validated view of a config_version body.

Pure: takes the JSON dict the board approved, returns frozen dataclasses.
Every rule in the engine reads its numbers from here. Money is agorot.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from app.domain.enums import Category, DocumentType, Tier


class ConfigError(ValueError):
    pass


class Seat(StrEnum):
    """A place on an approval panel. The service maps staff roles to seats."""

    COORDINATOR = "coordinator"
    CHAIR = "chair"
    COMMITTEE = "committee"


class SplitPolicy(StrEnum):
    """Q20, Q23: what happens when a fully voted panel is split."""

    ESCALATE = "escalate"  # to a larger panel; earlier votes stand
    CHAIR_DECIDES = "chair_decides"  # tier E: must not stall


@dataclass(frozen=True)
class SplitRule:
    policy: SplitPolicy
    escalate_to: Tier | None = None


class MedianRounding(StrEnum):
    UP = "up"
    DOWN = "down"


class Guideline(StrEnum):
    APPROVE_FULL = "approve_full"
    PARTIAL_OR_CONDITIONAL = "approve_partial_or_conditional"
    REFER = "refer_small_grant_with_reason"
    DECLINE = "decline_with_referral"


@dataclass(frozen=True)
class ApprovalRule:
    seats: Mapping[Seat, int]  # every seat must vote
    min_for: int  # votes in favour needed once all seats have voted

    @property
    def total_seats(self) -> int:
        return sum(self.seats.values())


@dataclass(frozen=True)
class TierRule:
    tier: Tier
    # Q24: tier bands are lower-bound inclusive, so A/B/C use an exclusive
    # upper bound (exactly ₪500 is B). Tier E is a ceiling on the emergency
    # path and is inclusive (exactly ₪1,500 is E).
    upper_bound: int | None  # None = no upper bound
    upper_inclusive: bool
    approval: ApprovalRule
    sla_working_days: int | None
    sla_hours: int | None
    requires_scoring: bool
    requires_intake_call: bool  # AP-5
    requires_ratification: bool
    on_split: SplitRule | None  # None: a split cannot happen on this panel
    # Q26: for an unscored tier, whether a case escalated from it must be
    # scored at the higher tier, and how many extra requests (one document
    # or one phone verification) the escalated panel may make.
    escalation_requires_scoring: bool
    escalation_extra_requests: int | None  # None = no limit beyond the tier's own rules

    def contains(self, amount: int) -> bool:
        if self.upper_bound is None:
            return True
        return amount <= self.upper_bound if self.upper_inclusive else amount < self.upper_bound


@dataclass(frozen=True)
class Caps:
    per_grant: int
    household_amount_per_year: int
    household_grants_per_year: int
    per_category_per_year: Mapping[Category, int]  # AP-13


@dataclass(frozen=True)
class ScoreBand:
    min: int
    max: int
    guideline: Guideline


@dataclass(frozen=True)
class NeedBand:
    below_percent: int | None  # of the poverty line; None = no upper bound
    score: int


@dataclass(frozen=True)
class NeedScoring:
    """AP-8: income per standard person (נפשות תקניות) against Bituach
    Leumi's poverty line (Q14, Q22)."""

    enabled: bool
    poverty_line_per_standard_person: int | None  # agorot per month
    poverty_line_year: int | None
    poverty_line_source: str | None
    standard_persons: tuple[int, ...]  # hundredths, for household sizes 1..n
    extra_person: int  # hundredths added for each person beyond the table
    bands: tuple[NeedBand, ...]


@dataclass(frozen=True)
class SuggestionRange:
    low: int
    high: int


@dataclass(frozen=True)
class RightsSuggestion:
    """AP-7: suggested 'alternatives' score from the rights check."""

    eligible_not_claimed: SuggestionRange
    claim_in_progress: SuggestionRange
    resolved: SuggestionRange


@dataclass(frozen=True)
class DocumentRules:
    by_category: Mapping[Category, tuple[tuple[DocumentType, ...], ...]]
    car_second_quote_above: int
    income_proof_from_tier: Tier
    referral_letter_from_tier: Tier  # AP-2
    recognised_referral_waives: tuple[DocumentType, ...]  # AP-1; see Q13


@dataclass(frozen=True)
class ExcludedPurpose:
    code: str
    labels: Mapping[str, str]


@dataclass(frozen=True)
class Conditions:
    repeat_rent_requires_coaching: bool
    repeat_window_days: int
    coaching_default_org: str


@dataclass(frozen=True)
class Budget:
    monthly_allocation: int | None  # BOARD
    reserve_percent: int
    emergency_only_threshold_percent: int


@dataclass(frozen=True)
class RulesConfig:
    version: int
    tiers: Mapping[Tier, TierRule]
    caps: Caps
    cooling_off_days: int
    max_score: int
    median_rounding: MedianRounding
    score_bands: tuple[ScoreBand, ...]
    need: NeedScoring
    rights: RightsSuggestion
    documents: DocumentRules
    categories: frozenset[Category]
    excluded_purposes: tuple[ExcludedPurpose, ...]
    conditions: Conditions
    budget: Budget
    reconfirm_after_days: int
    alternate_assign_within_working_days: int  # Q21
    boundary_flag_window: int  # Q21, agorot
    vote_reasoning_max_chars: int  # Q20
    public_min_cell: int
    sla_breach_alert_percent: int
    consent_version: str

    def tier(self, tier: Tier) -> TierRule:
        return self.tiers[tier]

    def excluded(self, code: str) -> ExcludedPurpose | None:
        return next((p for p in self.excluded_purposes if p.code == code), None)


ORDERED_TIERS = (Tier.A, Tier.B, Tier.C)


def _req(body: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in body:
        raise ConfigError(f"missing {path}{key}")
    return body[key]


def _non_negative_int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfigError(f"{path} must be a non-negative integer")
    return value


def _optional_int(value: Any, path: str) -> int | None:
    return None if value is None else _non_negative_int(value, path)


def _range(raw: Sequence[int], path: str) -> SuggestionRange:
    low, high = (_non_negative_int(v, path) for v in raw)
    if low > high:
        raise ConfigError(f"{path} low is above high")
    return SuggestionRange(low, high)


def _approval(raw: Mapping[str, Any], path: str) -> ApprovalRule:
    seats = {Seat(k): _non_negative_int(v, f"{path}.seats.{k}") for k, v in raw["seats"].items()}
    rule = ApprovalRule(seats=seats, min_for=_non_negative_int(raw["min_for"], f"{path}.min_for"))
    if not 1 <= rule.min_for <= rule.total_seats:
        raise ConfigError(f"{path}.min_for must be between 1 and the number of seats")
    return rule


def _tier(tier: Tier, raw: Mapping[str, Any]) -> TierRule:
    path = f"tiers.{tier.value}"
    sla = _req(raw, "sla", f"{path}.")
    return TierRule(
        tier=tier,
        upper_bound=_optional_int(
            raw.get("max_amount", raw.get("below_amount")), f"{path}.amount bound"
        ),
        upper_inclusive="max_amount" in raw,
        approval=_approval(_req(raw, "approval", f"{path}."), f"{path}.approval"),
        sla_working_days=_optional_int(sla.get("working_days"), f"{path}.sla.working_days"),
        sla_hours=_optional_int(sla.get("hours"), f"{path}.sla.hours"),
        requires_scoring=bool(raw.get("scoring", False)),
        requires_intake_call=bool(raw.get("intake_call", False)),
        requires_ratification=bool(raw.get("ratify", False)),
        on_split=_split_rule(raw.get("on_split"), path),
        escalation_requires_scoring=bool(raw.get("escalation_requires_scoring", True)),
        escalation_extra_requests=_optional_int(
            raw.get("escalation_extra_requests"), f"{path}.escalation_extra_requests"
        ),
    )


def _split_rule(raw: Any, path: str) -> SplitRule | None:
    if raw is None:
        return None
    if raw == SplitPolicy.CHAIR_DECIDES.value:
        return SplitRule(SplitPolicy.CHAIR_DECIDES)
    if isinstance(raw, str) and raw.startswith("escalate_to_"):
        return SplitRule(SplitPolicy.ESCALATE, Tier(raw.removeprefix("escalate_to_")))
    raise ConfigError(f"{path}.on_split must be escalate_to_<tier> or chair_decides")


def _check_tiers(tiers: Mapping[Tier, TierRule]) -> None:
    a, b = (tiers[t] for t in (Tier.A, Tier.B))
    for rule in (a, b):
        if rule.upper_bound is None or rule.upper_inclusive:
            raise ConfigError(f"tiers.{rule.tier.value} needs below_amount (Q24)")
    if not a.upper_bound < b.upper_bound:  # type: ignore[operator]
        raise ConfigError("tier bounds must satisfy A < B")
    if tiers[Tier.C].upper_bound is not None:
        raise ConfigError("tier C has no upper bound")
    if tiers[Tier.E].upper_bound is None or not tiers[Tier.E].upper_inclusive:
        raise ConfigError("tier E needs max_amount")
    for rule in tiers.values():
        if (rule.sla_working_days is None) == (rule.sla_hours is None):
            raise ConfigError(
                f"tiers.{rule.tier.value}.sla needs exactly one of working_days, hours"
            )
        split = rule.on_split
        if split is None:
            continue
        if split.policy is SplitPolicy.ESCALATE:
            assert split.escalate_to is not None
            # Escalation adds committee members (A: 1 -> B: 2 -> C: 3).
            target = tiers[split.escalate_to].approval.seats.get(Seat.COMMITTEE, 0)
            if target <= rule.approval.seats.get(Seat.COMMITTEE, 0):
                raise ConfigError(
                    f"tiers.{rule.tier.value}.on_split must escalate to more committee seats"
                )
        elif Seat.CHAIR not in rule.approval.seats:
            raise ConfigError(f"tiers.{rule.tier.value}.on_split chair_decides needs a chair seat")


def _check_bands(bands: tuple[ScoreBand, ...], max_score: int) -> None:
    covered = sorted((b.min, b.max) for b in bands)
    expected = 0
    for low, high in covered:
        if low != expected or high < low:
            raise ConfigError("score bands must cover 0..max_total without gaps or overlaps")
        expected = high + 1
    if expected != max_score + 1:
        raise ConfigError("score bands must cover 0..max_total without gaps or overlaps")


def _hundredths(value: Any, path: str) -> int:
    try:
        scaled = Decimal(str(value)) * 100
    except InvalidOperation as exc:
        raise ConfigError(f"{path} must be a number") from exc
    if scaled != scaled.to_integral_value() or scaled <= 0:
        raise ConfigError(f"{path} must be positive with at most two decimals")
    return int(scaled)


def _need_bands(percents: Sequence[Any]) -> tuple[NeedBand, ...]:
    """[100, 125, 150] -> below 100%: 3, below 125%: 2, below 150%: 1, else 0."""
    limits = [_non_negative_int(p, "scoring.need_bands_percent") for p in percents]
    if not limits or limits != sorted(set(limits)):
        raise ConfigError("scoring.need_bands_percent must be non-empty and strictly ascending")
    top = len(limits)
    return (*(NeedBand(p, top - i) for i, p in enumerate(limits)), NeedBand(None, 0))


def parse_config(version: int, body: Mapping[str, Any]) -> RulesConfig:
    if body.get("currency_unit") != "agorot":
        raise ConfigError("currency_unit must be 'agorot'")

    tiers_raw = _req(body, "tiers", "")
    tiers = {t: _tier(t, _req(tiers_raw, t.value, "tiers.")) for t in Tier}
    _check_tiers(tiers)

    caps_raw = _req(body, "caps", "")
    caps = Caps(
        per_grant=_non_negative_int(caps_raw["per_grant"], "caps.per_grant"),
        household_amount_per_year=_non_negative_int(
            caps_raw["household_amount_per_year"], "caps.household_amount_per_year"
        ),
        household_grants_per_year=_non_negative_int(
            caps_raw["household_grants_per_year"], "caps.household_grants_per_year"
        ),
        per_category_per_year={
            Category(k): _non_negative_int(v, f"caps.per_category_per_year.{k}")
            for k, v in caps_raw.get("per_category_per_year", {}).items()
        },
    )

    scoring = _req(body, "scoring", "")
    max_score = _non_negative_int(scoring["max_total"], "scoring.max_total")
    bands = tuple(
        ScoreBand(b["min"], b["max"], Guideline(b["guideline"])) for b in scoring["bands"]
    )
    _check_bands(bands, max_score)

    scale = _req(scoring, "equivalence_scale", "scoring.")
    persons = tuple(_hundredths(x, "scoring.equivalence_scale") for x in scale)
    if not persons or list(persons) != sorted(persons):
        raise ConfigError("scoring.equivalence_scale must be non-empty and ascending")
    need = NeedScoring(
        enabled=bool(scoring.get("need_suggestion_enabled", False)),
        poverty_line_per_standard_person=_optional_int(
            scoring.get("poverty_line_monthly_agorot"), "scoring.poverty_line_monthly_agorot"
        ),
        poverty_line_year=_optional_int(
            scoring.get("poverty_line_year"), "scoring.poverty_line_year"
        ),
        poverty_line_source=scoring.get("poverty_line_source"),
        standard_persons=persons,
        extra_person=_hundredths(
            _req(scoring, "equivalence_extra_person", "scoring."),
            "scoring.equivalence_extra_person",
        ),
        bands=_need_bands(_req(scoring, "need_bands_percent", "scoring.")),
    )

    rights_raw = _req(body, "rights_suggestion", "")
    rights = RightsSuggestion(
        eligible_not_claimed=_range(rights_raw["eligible_not_claimed"], "rights.eligible"),
        claim_in_progress=_range(rights_raw["claim_in_progress"], "rights.in_progress"),
        resolved=_range(rights_raw["resolved"], "rights.resolved"),
    )

    docs_raw = _req(body, "documents", "")
    documents = DocumentRules(
        by_category={
            Category(cat): tuple(tuple(DocumentType(d) for d in group) for group in groups)
            for cat, groups in docs_raw["by_category"].items()
        },
        car_second_quote_above=_non_negative_int(
            docs_raw["car_second_quote_above"], "documents.car_second_quote_above"
        ),
        income_proof_from_tier=Tier(docs_raw["income_proof_from_tier"]),
        referral_letter_from_tier=Tier(docs_raw["referral_letter_from_tier"]),
        recognised_referral_waives=tuple(
            DocumentType(d) for d in docs_raw.get("recognised_referral_waives", [])
        ),
    )

    cond = body.get("conditions", {})
    budget = body.get("budget", {})
    return RulesConfig(
        version=version,
        tiers=tiers,
        caps=caps,
        cooling_off_days=_non_negative_int(_req(body, "cooling_off_days", ""), "cooling_off_days"),
        max_score=max_score,
        median_rounding=MedianRounding(scoring.get("median_rounding", "up")),
        score_bands=bands,
        need=need,
        rights=rights,
        documents=documents,
        categories=frozenset(Category(c) for c in _req(body, "categories", "")),
        excluded_purposes=tuple(
            ExcludedPurpose(
                code=p["code"], labels={k[6:]: v for k, v in p.items() if k.startswith("label_")}
            )
            for p in body.get("excluded_purposes", [])
        ),
        conditions=Conditions(
            repeat_rent_requires_coaching=bool(cond.get("repeat_rent_requires_coaching", False)),
            repeat_window_days=_non_negative_int(
                cond.get("repeat_window_days", 365), "conditions.repeat_window_days"
            ),
            coaching_default_org=str(cond.get("coaching_default_org", "")),
        ),
        budget=Budget(
            monthly_allocation=_optional_int(
                budget.get("monthly_allocation"), "budget.monthly_allocation"
            ),
            reserve_percent=_non_negative_int(
                budget.get("reserve_percent", 0), "budget.reserve_percent"
            ),
            emergency_only_threshold_percent=_non_negative_int(
                budget.get("emergency_only_threshold_percent", 0),
                "budget.emergency_only_threshold_percent",
            ),
        ),
        reconfirm_after_days=_non_negative_int(
            body.get("payment", {}).get("reconfirm_after_days", 14), "payment.reconfirm_after_days"
        ),
        alternate_assign_within_working_days=_non_negative_int(
            body.get("alternates", {}).get("assign_within_working_days", 2),
            "alternates.assign_within_working_days",
        ),
        boundary_flag_window=_non_negative_int(
            body.get("audit", {}).get("boundary_flag_window_agorot", 20_000),
            "audit.boundary_flag_window_agorot",
        ),
        vote_reasoning_max_chars=_non_negative_int(
            body.get("votes", {}).get("reasoning_max_chars", 200), "votes.reasoning_max_chars"
        ),
        public_min_cell=_non_negative_int(
            body.get("public_stats", {}).get("min_cell", 5), "public_stats.min_cell"
        ),
        sla_breach_alert_percent=_non_negative_int(
            body.get("sla", {}).get("breach_alert_percent", 20), "sla.breach_alert_percent"
        ),
        consent_version=str(_req(body, "consent_version", "")),
    )


def board_placeholders(cfg: RulesConfig) -> list[str]:
    """Values the board has not set yet. Production refuses a config with any."""
    missing = []
    if cfg.need.enabled and cfg.need.poverty_line_per_standard_person is None:
        missing.append("scoring.poverty_line_monthly_agorot")
    if cfg.budget.monthly_allocation is None:
        missing.append("budget.monthly_allocation")
    return missing
