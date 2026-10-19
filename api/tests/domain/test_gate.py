from dataclasses import replace
from datetime import date

import pytest

from app.domain.caps import PriorGrant, exceeded_caps, headroom
from app.domain.enums import Category, ReferrerStatus
from app.domain.gate import GateCheck, GateInput, InsiderEntry, run_gate
from tests.domain.helpers import cfg

C = cfg()
TODAY = date(2026, 10, 19)
BASE = GateInput(
    category=Category.RENT,
    amount=120_000,
    urgency=False,
    household_id_hashes=frozenset({"applicant-h", "partner-h"}),
    prior_grants=(),
    consent_version="2026-1",
    today=TODAY,
)


def codes(inp: GateInput, insiders: tuple[InsiderEntry, ...] = ()) -> dict[GateCheck, list[str]]:
    r = run_gate(inp, insiders, C)
    return {c.check: [x.code for x in c.reasons] for c in r.checks}


def test_clean_application_passes_every_check() -> None:
    r = run_gate(BASE, (), C)
    assert r.passed
    assert r.config_version == 1
    assert not r.referral_recognised
    assert r.check(GateCheck.CONSENT).passed


# --- check 1: category and exclusions (AP-10)


def test_ap10_excluded_purpose_fails_category_check() -> None:
    r = run_gate(replace(BASE, excluded_purpose="food"), (), C)
    assert not r.passed
    reason = r.check(GateCheck.CATEGORY).reasons[0]
    assert (reason.code, reason.params) == ("excluded_purpose", {"code": "food"})


def test_ap10_exclusion_list_comes_from_config() -> None:
    narrower = cfg(**{"excluded_purposes": [{"code": "luxury", "label_he": "מותרות"}]})
    with pytest.raises(ValueError, match="unknown excluded purpose"):
        run_gate(replace(BASE, excluded_purpose="food"), (), narrower)


def test_category_not_offered() -> None:
    c = cfg(categories=["car"])
    r = run_gate(BASE, (), c)
    assert r.check(GateCheck.CATEGORY).reasons[0].code == "category_not_offered"


@pytest.mark.parametrize(("chair", "passed"), [(False, False), (True, True)])
def test_other_category_needs_chair(chair: bool, passed: bool) -> None:
    inp = replace(BASE, category=Category.OTHER, chair_approved_other=chair)
    assert run_gate(inp, (), C).check(GateCheck.CATEGORY).passed is passed


# --- check 2: insiders


@pytest.mark.parametrize(
    ("entry", "blocked"),
    [
        (InsiderEntry("partner-h", date(2020, 1, 1), None), True),
        (InsiderEntry("applicant-h", date(2020, 1, 1), date(2026, 10, 19)), True),
        (InsiderEntry("applicant-h", date(2020, 1, 1), date(2026, 10, 18)), False),  # ended
        (InsiderEntry("applicant-h", date(2026, 10, 20), None), False),  # not yet
        (InsiderEntry("someone-else", date(2020, 1, 1), None), False),
    ],
)
def test_insider_check(entry: InsiderEntry, blocked: bool) -> None:
    result = codes(BASE, (entry,))[GateCheck.NOT_INSIDER]
    assert result == (["household_insider"] if blocked else ["no_insider"])


# --- check 3: caps (household and AP-13 per category)


def grant(
    day: date, amount: int, cat: Category = Category.CAR, paid: date | None = None
) -> PriorGrant:
    return PriorGrant(decided_on=day, amount=amount, category=cat, paid_on=paid)


def test_ap13_second_car_request_in_a_year_fails_on_category_cap() -> None:
    inp = replace(BASE, category=Category.CAR, prior_grants=(grant(date(2026, 2, 1), 100_000),))
    assert codes(inp)[GateCheck.WITHIN_CAP] == ["cap_category_count"]


def test_ap13_last_years_grant_does_not_count() -> None:
    inp = replace(BASE, category=Category.CAR, prior_grants=(grant(date(2025, 12, 31), 100_000),))
    assert codes(inp)[GateCheck.WITHIN_CAP] == ["within_caps"]


def test_household_caps_and_board_exception() -> None:
    prior = tuple(grant(date(2026, m, 1), 300_000, Category.MEDICAL) for m in (1, 2, 3))
    inp = replace(BASE, amount=600_000, prior_grants=prior)
    assert codes(inp)[GateCheck.WITHIN_CAP] == [
        "cap_per_grant",
        "cap_household_amount",
        "cap_household_count",
    ]
    excepted = run_gate(replace(inp, board_cap_exception=True), (), C)
    check = excepted.check(GateCheck.WITHIN_CAP)
    assert check.passed
    assert check.reasons[-1].code == "board_cap_exception"


def test_headroom_for_the_ui() -> None:
    prior = (grant(date(2026, 3, 1), 200_000, Category.CAR),)
    room = headroom(prior, Category.CAR, 2026, C)
    assert (room.amount_remaining, room.grants_remaining, room.category_grants_remaining) == (
        800_000,
        2,
        0,
    )
    assert headroom((), Category.OTHER, 2026, C).category_grants_remaining is None
    assert exceeded_caps(1, room, Category.CAR)[0].code == "cap_category_count"


# --- check 4: cooling-off


@pytest.mark.parametrize(
    ("paid", "urgent", "override", "code"),
    [
        (None, False, False, "no_previous_payment"),
        (date(2026, 4, 22), False, False, "cooling_off_elapsed"),  # exactly 180 days
        (date(2026, 4, 23), False, False, "cooling_off"),
        (date(2026, 9, 1), True, False, "cooling_off"),  # urgent but no chair
        (date(2026, 9, 1), False, True, "cooling_off"),  # chair but not urgent
        (date(2026, 9, 1), True, True, "cooling_off_overridden"),
    ],
)
def test_cooling_off(paid: date | None, urgent: bool, override: bool, code: str) -> None:
    prior = (grant(date(2025, 1, 1), 10_000, Category.BABY, paid),) if paid else ()
    inp = replace(BASE, prior_grants=prior, urgency=urgent, chair_cooling_off_override=override)
    assert codes(inp)[GateCheck.COOLING_OFF] == [code]


# --- check 5: consent


@pytest.mark.parametrize("version", [None, "2025-1"])
def test_consent_must_be_current(version: str | None) -> None:
    assert codes(replace(BASE, consent_version=version))[GateCheck.CONSENT] == [
        "consent_missing_or_old"
    ]


# --- AP-1: referral recognition


@pytest.mark.parametrize(
    ("status", "recognised"),
    [
        (None, False),
        (ReferrerStatus.PENDING, False),
        (ReferrerStatus.SUSPENDED, False),
        (ReferrerStatus.RECOGNISED, True),
    ],
)
def test_ap1_only_recognised_referrers_count(
    status: ReferrerStatus | None, recognised: bool
) -> None:
    assert run_gate(replace(BASE, referrer_status=status), (), C).referral_recognised is recognised
