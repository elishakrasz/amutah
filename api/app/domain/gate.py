"""Eligibility gate: five checks, all must pass. The result is a
recommendation; the coordinator records the outcome (D16)."""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from app.domain.caps import PriorGrant, exceeded_caps, headroom
from app.domain.config import RulesConfig
from app.domain.enums import Category, ReferrerStatus
from app.domain.results import Reason


class GateCheck(StrEnum):
    CATEGORY = "category"
    NOT_INSIDER = "not_insider"
    WITHIN_CAP = "within_cap"
    COOLING_OFF = "cooling_off"
    CONSENT = "consent"


@dataclass(frozen=True)
class InsiderEntry:
    national_id_hash: str
    effective_from: date
    effective_to: date | None

    def active_on(self, day: date) -> bool:
        return self.effective_from <= day and (
            self.effective_to is None or day <= self.effective_to
        )


@dataclass(frozen=True)
class GateInput:
    category: Category
    amount: int  # agorot requested
    urgency: bool
    household_id_hashes: frozenset[str]  # applicant and partner
    prior_grants: tuple[PriorGrant, ...]
    consent_version: str | None
    today: date
    referrer_status: ReferrerStatus | None = None  # None = direct application
    excluded_purpose: str | None = None  # AP-10, selected by the coordinator
    chair_approved_other: bool = False
    chair_cooling_off_override: bool = False
    board_cap_exception: bool = False


@dataclass(frozen=True)
class CheckResult:
    check: GateCheck
    passed: bool
    reasons: tuple[Reason, ...]


@dataclass(frozen=True)
class GateResult:
    checks: tuple[CheckResult, ...]
    # AP-1: counts as referred only if the referrer is recognised right now.
    referral_recognised: bool
    config_version: int

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def check(self, which: GateCheck) -> CheckResult:
        return next(c for c in self.checks if c.check is which)


def _category(inp: GateInput, cfg: RulesConfig) -> CheckResult:
    if inp.excluded_purpose is not None:
        excluded = cfg.excluded(inp.excluded_purpose)
        if excluded is None:
            raise ValueError(f"unknown excluded purpose {inp.excluded_purpose!r}")
        return CheckResult(
            GateCheck.CATEGORY, False, (Reason("excluded_purpose", {"code": excluded.code}),)
        )
    if inp.category not in cfg.categories:
        return CheckResult(GateCheck.CATEGORY, False, (Reason("category_not_offered"),))
    if inp.category is Category.OTHER and not inp.chair_approved_other:
        return CheckResult(GateCheck.CATEGORY, False, (Reason("other_needs_chair_approval"),))
    return CheckResult(GateCheck.CATEGORY, True, (Reason("category_ok"),))


def _not_insider(inp: GateInput, insiders: tuple[InsiderEntry, ...]) -> CheckResult:
    hit = any(
        i.national_id_hash in inp.household_id_hashes and i.active_on(inp.today) for i in insiders
    )
    if hit:
        # Never say which household member matched.
        return CheckResult(GateCheck.NOT_INSIDER, False, (Reason("household_insider"),))
    return CheckResult(GateCheck.NOT_INSIDER, True, (Reason("no_insider"),))


def _within_cap(inp: GateInput, cfg: RulesConfig) -> CheckResult:
    room = headroom(inp.prior_grants, inp.category, inp.today.year, cfg)
    exceeded = exceeded_caps(inp.amount, room, inp.category)
    if not exceeded:
        return CheckResult(GateCheck.WITHIN_CAP, True, (Reason("within_caps"),))
    if inp.board_cap_exception:
        return CheckResult(GateCheck.WITHIN_CAP, True, (*exceeded, Reason("board_cap_exception")))
    return CheckResult(GateCheck.WITHIN_CAP, False, exceeded)


def _cooling_off(inp: GateInput, cfg: RulesConfig) -> CheckResult:
    paid = [g.paid_on for g in inp.prior_grants if g.paid_on is not None]
    if not paid:
        return CheckResult(GateCheck.COOLING_OFF, True, (Reason("no_previous_payment"),))
    ends = max(paid) + timedelta(days=cfg.cooling_off_days)
    if inp.today >= ends:
        return CheckResult(GateCheck.COOLING_OFF, True, (Reason("cooling_off_elapsed"),))
    if inp.urgency and inp.chair_cooling_off_override:
        return CheckResult(
            GateCheck.COOLING_OFF, True, (Reason("cooling_off_overridden", {"ends": ends}),)
        )
    return CheckResult(GateCheck.COOLING_OFF, False, (Reason("cooling_off", {"ends": ends}),))


def _consent(inp: GateInput, cfg: RulesConfig) -> CheckResult:
    if inp.consent_version == cfg.consent_version:
        return CheckResult(GateCheck.CONSENT, True, (Reason("consent_current"),))
    return CheckResult(
        GateCheck.CONSENT,
        False,
        (Reason("consent_missing_or_old", {"needed": cfg.consent_version}),),
    )


def run_gate(inp: GateInput, insiders: tuple[InsiderEntry, ...], cfg: RulesConfig) -> GateResult:
    return GateResult(
        checks=(
            _category(inp, cfg),
            _not_insider(inp, insiders),
            _within_cap(inp, cfg),
            _cooling_off(inp, cfg),
            _consent(inp, cfg),
        ),
        referral_recognised=inp.referrer_status is ReferrerStatus.RECOGNISED,
        config_version=cfg.version,
    )
