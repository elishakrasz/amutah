import pytest

from app.domain.income import IncomeResult, per_standard_person, standard_persons, suggest_need
from tests.domain.helpers import POVERTY_LINE, cfg

C = cfg()


@pytest.mark.parametrize(
    ("size", "weight"),
    [(1, 125), (2, 200), (3, 265), (4, 320), (5, 375), (9, 560), (10, 600), (12, 680)],
)
def test_standard_persons_scale(size: int, weight: int) -> None:
    assert standard_persons(size, C) == weight


def test_standard_persons_needs_a_person() -> None:
    with pytest.raises(ValueError):
        standard_persons(0, C)


def test_examples_from_the_board_answer() -> None:
    family = per_standard_person(1_000_000, 200_000, 0, 2, 3, C)  # ₪12,000, five people
    single = per_standard_person(400_000, 0, 0, 1, 0, C)  # ₪4,000, one person
    assert family.per_standard_person == single.per_standard_person == 320_000
    assert family.divisor_label == "3.75"
    assert single.divisor_label == "1.25"


def test_ap8_same_figures_same_result() -> None:
    a = per_standard_person(733_333, 41_000, 1, 2, 4, C)
    b = per_standard_person(733_333, 41_000, 1, 2, 4, C)
    assert a == b
    assert suggest_need(a, C) == suggest_need(b, C)


@pytest.mark.parametrize(
    "args",
    [(-1, 0, 0, 1, 0), (0, -1, 0, 1, 0), (0, 0, -1, 1, 0), (0, 0, 0, 0, 1), (0, 0, 0, 1, -1)],
)
def test_invalid_worksheet(args: tuple[int, int, int, int, int]) -> None:
    with pytest.raises(ValueError):
        per_standard_person(*args, C)


@pytest.mark.parametrize(
    ("per_person", "score"),
    [
        (POVERTY_LINE - 1, 3),  # below the line
        (POVERTY_LINE, 2),  # exactly 100% is in the 100-125% band
        (POVERTY_LINE * 125 // 100 - 1, 2),
        (POVERTY_LINE * 125 // 100, 1),
        (POVERTY_LINE * 150 // 100 - 1, 1),
        (POVERTY_LINE * 150 // 100, 0),
        (POVERTY_LINE * 3, 0),
    ],
)
def test_ap8_need_suggestion_bands(per_person: int, score: int) -> None:
    r = IncomeResult(per_person * 125 // 100, 1, 125, per_person)
    s = suggest_need(r, C)
    assert s is not None
    assert (s.low, s.high, s.reason.code) == (score, score, "need_from_income")
    assert s.reason.params["divisor"] == "1.25"


@pytest.mark.parametrize(
    "overrides",
    [
        {"scoring.poverty_line_monthly_agorot": None},
        {"scoring.need_suggestion_enabled": False},
    ],
)
def test_no_suggestion_when_off_or_unset(overrides: dict[str, object]) -> None:
    c = cfg(**overrides)
    assert suggest_need(per_standard_person(100, 0, 0, 1, 0, c), c) is None


def test_q22_suggestion_cites_its_source() -> None:
    # Couple with three children, ₪12,000: ₪3,200 per standard person,
    # below ₪3,547, so the advisory need score is 3.
    s = suggest_need(per_standard_person(1_200_000, 0, 0, 2, 3, C), C)
    assert s is not None
    assert s.low == 3
    assert s.reason.params["poverty_line_year"] == 2024
    assert s.reason.params["poverty_line_source"] == "NII poverty report 2024"


@pytest.mark.parametrize(
    ("percent", "score"),
    [
        (100, 2),  # at the line: 100% to below 125%
        (125, 1),  # 125% to below 150%
        (150, 0),  # 150% and above
    ],
)
def test_q24_each_boundary_lands_in_the_upper_band(percent: int, score: int) -> None:
    """Lower bound inclusive: a household at a threshold has reached the next
    band up in means, so it gets the lower score."""
    per_person = POVERTY_LINE * percent // 100
    assert per_person * 100 == POVERTY_LINE * percent  # exact at ₪3,547
    s = suggest_need(IncomeResult(per_person * 125 // 100, 1, 125, per_person), C)
    assert s is not None
    assert s.low == score
    just_below = suggest_need(IncomeResult(0, 1, 125, per_person - 1), C)
    assert just_below is not None
    assert just_below.low == score + 1
