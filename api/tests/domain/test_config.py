from typing import Any

import pytest

from app.domain.config import (
    ConfigError,
    Seat,
    SplitPolicy,
    SplitRule,
    board_placeholders,
    parse_config,
)
from app.domain.enums import Category, Tier
from app.scripts.demo_config import CONFIG_V1
from tests.domain.helpers import DELETE, body, cfg


def test_demo_config_parses_and_lists_board_placeholders() -> None:
    c = parse_config(1, CONFIG_V1)
    assert board_placeholders(c) == ["budget.monthly_allocation"]
    assert board_placeholders(cfg()) == []
    unset = cfg(**{"scoring.poverty_line_monthly_agorot": None})
    assert board_placeholders(unset) == ["scoring.poverty_line_monthly_agorot"]
    off = cfg(
        **{"scoring.poverty_line_monthly_agorot": None, "scoring.need_suggestion_enabled": False}
    )
    assert board_placeholders(off) == []


def test_board_answers_are_encoded() -> None:
    c = cfg()
    a = c.tier(Tier.A)
    assert (a.upper_bound, a.upper_inclusive) == (50_000, False)  # Q24: ₪500 is tier B
    assert not a.contains(50_000) and a.contains(49_999)
    e = c.tier(Tier.E)
    assert (e.upper_bound, e.upper_inclusive) == (150_000, True)  # ₪1,500 is still E
    assert c.tier(Tier.C).contains(10**9)
    assert c.tier(Tier.B).approval.seats == {Seat.COMMITTEE: 2}
    assert c.tier(Tier.B).approval.min_for == 2  # both must agree
    assert c.tier(Tier.C).approval.total_seats == 3
    assert c.tier(Tier.C).approval.min_for == 2  # two of three
    assert c.median_rounding.value == "up"  # Q2
    assert c.need.standard_persons[:5] == (125, 200, 265, 320, 375)  # Q14
    assert c.need.extra_person == 40
    assert c.need.poverty_line_per_standard_person == 354_700  # Q22
    assert (c.need.poverty_line_year, c.need.enabled) == (2024, True)
    assert [(b.below_percent, b.score) for b in c.need.bands] == [
        (100, 3),
        (125, 2),
        (150, 1),
        (None, 0),
    ]
    assert c.tier(Tier.B).on_split == SplitRule(SplitPolicy.ESCALATE, Tier.C)  # Q20
    assert c.tier(Tier.A).on_split == SplitRule(SplitPolicy.ESCALATE, Tier.B)  # Q23
    assert c.tier(Tier.E).on_split == SplitRule(SplitPolicy.CHAIR_DECIDES)  # Q23
    assert c.tier(Tier.C).on_split is None  # three seats cannot split
    assert not c.tier(Tier.A).escalation_requires_scoring  # Q26
    assert c.tier(Tier.A).escalation_extra_requests == 1
    assert c.tier(Tier.B).escalation_requires_scoring  # default
    assert c.tier(Tier.B).escalation_extra_requests is None
    assert c.alternate_assign_within_working_days == 2  # Q21
    assert c.boundary_flag_window == 20_000  # ₪200
    assert c.excluded("food") is not None
    assert c.excluded("nope") is None
    assert c.excluded_purposes[0].labels["he"] == "החזר חובות"
    assert c.caps.per_category_per_year[Category.CAR] == 1


def test_optional_sections_have_defaults() -> None:
    b = body()
    for key in ("conditions", "budget", "payment", "public_stats", "sla", "excluded_purposes"):
        del b[key]
    del b["scoring"]["median_rounding"]
    del b["caps"]["per_category_per_year"]
    for key in ("alternates", "audit", "votes"):
        del b[key]
    for key in ("need_suggestion_enabled", "poverty_line_monthly_agorot", "poverty_line_year"):
        del b["scoring"][key]
    del b["documents"]["recognised_referral_waives"]
    c = parse_config(2, b)
    assert c.reconfirm_after_days == 14
    assert c.budget.monthly_allocation is None
    assert c.caps.per_category_per_year == {}
    assert not c.need.enabled
    assert c.vote_reasoning_max_chars == 200


BAD: list[tuple[dict[str, Any], str]] = [
    ({"currency_unit": "shekel"}, "agorot"),
    ({"tiers": DELETE}, "missing tiers"),
    ({"tiers.B.approval": DELETE}, "missing tiers.B.approval"),
    ({"tiers.B.approval.min_for": 3}, "min_for"),
    ({"tiers.B.approval.min_for": 0}, "min_for"),
    ({"tiers.A.below_amount": 300_000}, "A < B"),
    ({"tiers.A.below_amount": DELETE}, "below_amount"),
    ({"tiers.B.below_amount": DELETE, "tiers.B.max_amount": 300_000}, "below_amount"),
    ({"tiers.C.below_amount": 1}, "no upper bound"),
    ({"tiers.E.max_amount": DELETE}, "tier E needs max_amount"),
    ({"tiers.E.max_amount": DELETE, "tiers.E.below_amount": 1}, "tier E needs max_amount"),
    ({"tiers.A.sla": {"working_days": 2, "hours": 4}}, "exactly one"),
    ({"tiers.A.sla": {}}, "exactly one"),
    ({"caps.per_grant": -1}, "non-negative"),
    ({"caps.per_grant": True}, "non-negative"),
    ({"caps.per_grant": "5"}, "non-negative"),
    ({"scoring.bands": [{"min": 0, "max": 12, "guideline": "decline_with_referral"}]}, "cover"),
    ({"scoring.bands": [{"min": 1, "max": 13, "guideline": "decline_with_referral"}]}, "cover"),
    ({"scoring.bands": [{"min": 0, "max": -1, "guideline": "decline_with_referral"}]}, "cover"),
    ({"scoring.need_bands_percent": []}, "strictly ascending"),
    ({"scoring.need_bands_percent": [125, 100]}, "strictly ascending"),
    ({"scoring.need_bands_percent": [100, 100]}, "strictly ascending"),
    ({"scoring.equivalence_scale": []}, "non-empty and ascending"),
    ({"scoring.equivalence_scale": [2.0, 1.25]}, "non-empty and ascending"),
    ({"scoring.equivalence_scale": [1.255]}, "two decimals"),
    ({"scoring.equivalence_scale": [0]}, "positive"),
    ({"scoring.equivalence_extra_person": "x"}, "must be a number"),
    ({"tiers.B.on_split": "escalate_to_B"}, "more committee seats"),
    ({"tiers.C.on_split": "escalate_to_B"}, "more committee seats"),
    ({"tiers.B.on_split": "chair_decides"}, "needs a chair seat"),
    ({"tiers.B.on_split": "flip_a_coin"}, "on_split must be"),
    ({"rights_suggestion.resolved": [3, 2]}, "low is above high"),
    ({"cooling_off_days": DELETE}, "missing cooling_off_days"),
]


@pytest.mark.parametrize(("overrides", "message"), BAD)
def test_invalid_configs_are_rejected(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_config(1, body(**overrides))
