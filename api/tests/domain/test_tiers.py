import pytest

from app.domain.enums import Tier
from app.domain.tiers import assign_tier
from tests.domain.helpers import cfg

C = cfg()


@pytest.mark.parametrize(
    ("amount", "periods", "emergency", "tier", "reason"),
    [
        (1, 1, False, Tier.A, "amount_below"),
        (49_999, 1, False, Tier.A, "amount_below"),
        (50_000, 1, False, Tier.B, "amount_below"),  # Q24: exactly ₪500 is tier B
        (299_999, 1, False, Tier.B, "amount_below"),
        (300_000, 1, False, Tier.C, "amount_from"),  # Q24: exactly ₪3,000 is tier C
        (10_000, 2, False, Tier.C, "recurring"),
        (150_000, 1, True, Tier.E, "emergency"),  # emergency ceiling is inclusive
        (150_001, 1, True, Tier.B, "emergency_amount_above_max"),  # falls back by amount
        (60_000, 1, True, Tier.E, "emergency"),
        (10_000, 3, True, Tier.C, "emergency_not_for_recurring"),
        (200_000, 1, False, Tier.B, "amount_below"),
    ],
)
def test_tier_assignment(
    amount: int, periods: int, emergency: bool, tier: Tier, reason: str
) -> None:
    result = assign_tier(amount, periods, emergency, C)
    assert (result.tier, result.reason.code) == (tier, reason)


def test_emergency_over_limit_keeps_the_amount_tier() -> None:
    assert assign_tier(400_000, 1, True, C).tier is Tier.C
    small = assign_tier(160_000, 1, True, C)
    assert small.tier is Tier.B
    assert small.reason.code == "emergency_amount_above_max"


@pytest.mark.parametrize(("amount", "periods"), [(0, 1), (-5, 1), (100, 0)])
def test_invalid_requests(amount: int, periods: int) -> None:
    with pytest.raises(ValueError):
        assign_tier(amount, periods, False, C)


@pytest.mark.parametrize(
    ("amount", "flag"),
    [
        (29_999, None),
        (30_000, "50000"),  # ₪300: ₪200 below the tier A boundary
        (50_000, "50000"),
        (70_000, "50000"),  # ₪200 above
        (70_001, None),
        (149_000, "150000"),  # tier E boundary
        (290_000, "300000"),
        (320_001, None),
    ],
)
def test_q21_boundary_flag(amount: int, flag: str | None) -> None:
    from app.domain.tiers import boundary_flag

    r = boundary_flag(amount, C)
    assert (None if r is None else str(r.params["boundary"])) == flag


@pytest.mark.parametrize(
    ("amount", "periods", "emergency", "tier", "band"),
    [
        (150_000, 1, True, Tier.E, Tier.B),  # Q25: exactly ₪1,500 is E, reported as B
        (40_000, 1, True, Tier.E, Tier.A),
        (50_000, 1, True, Tier.E, Tier.B),
        (150_001, 1, True, Tier.B, Tier.B),
        (400_000, 1, False, Tier.C, Tier.C),
        (10_000, 2, False, Tier.C, Tier.C),
        (10_000, 2, True, Tier.C, Tier.C),
        (49_999, 1, False, Tier.A, Tier.A),
    ],
)
def test_q25_path_and_band_are_separate(
    amount: int, periods: int, emergency: bool, tier: Tier, band: Tier
) -> None:
    result = assign_tier(amount, periods, emergency, C)
    assert (result.tier, result.band) == (tier, band)
