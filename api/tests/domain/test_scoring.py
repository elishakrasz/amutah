import pytest

from app.domain.config import Guideline
from app.domain.enums import DecisionOutcome as O
from app.domain.enums import RightsStatus as R
from app.domain.scoring import (
    ScoreCard,
    case_score,
    departs_from_guideline,
    guideline,
    suggest_alternatives,
)
from tests.domain.helpers import cfg

C = cfg()


def test_scorecard_total_and_ranges() -> None:
    assert ScoreCard(3, 3, 3, 3, 1).total == 13
    with pytest.raises(ValueError, match="vulnerability"):
        ScoreCard(0, 0, 0, 0, 2)
    with pytest.raises(ValueError, match="need"):
        ScoreCard(-1, 0, 0, 0, 0)


@pytest.mark.parametrize(
    ("totals", "expected"),
    [
        ([7], 7),
        ([5, 9, 7], 7),
        ([8, 9], 9),  # 8.5 rounds up (Q2)
        ([8, 8], 8),
        ([2, 9, 9, 4], 7),  # middle pair 4 and 9 -> 6.5 -> 7
    ],
)
def test_median_rounds_up(totals: list[int], expected: int) -> None:
    assert case_score(totals, C) == expected


def test_median_rounding_down_is_configurable() -> None:
    assert case_score([8, 9], cfg(**{"scoring.median_rounding": "down"})) == 8


def test_median_needs_scores() -> None:
    with pytest.raises(ValueError):
        case_score([], C)


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (13, Guideline.APPROVE_FULL),
        (9, Guideline.APPROVE_FULL),
        (8, Guideline.PARTIAL_OR_CONDITIONAL),
        (6, Guideline.PARTIAL_OR_CONDITIONAL),
        (5, Guideline.REFER),
        (3, Guideline.REFER),
        (2, Guideline.DECLINE),
        (0, Guideline.DECLINE),
    ],
)
def test_guideline_bands(score: int, band: Guideline) -> None:
    assert guideline(score, C) is band


def test_guideline_out_of_range() -> None:
    with pytest.raises(ValueError):
        guideline(14, C)


@pytest.mark.parametrize(
    ("outcome", "band", "departs"),
    [
        (O.APPROVE_FULL, Guideline.APPROVE_FULL, False),
        (O.APPROVE_PARTIAL, Guideline.APPROVE_FULL, True),
        (O.APPROVE_CONDITIONAL, Guideline.PARTIAL_OR_CONDITIONAL, False),
        (O.APPROVE_PARTIAL, Guideline.REFER, True),  # small grant needs a written reason
        (O.REFER, Guideline.REFER, False),
        (O.DECLINE, Guideline.DECLINE, False),
        (O.APPROVE_FULL, Guideline.DECLINE, True),
    ],
)
def test_departure(outcome: O, band: Guideline, departs: bool) -> None:
    assert departs_from_guideline(outcome, band) is departs


@pytest.mark.parametrize(
    ("statuses", "low", "high", "code"),
    [
        ([R.CLAIMED, R.ELIGIBLE_NOT_CLAIMED], 0, 1, "rights_unclaimed"),
        ([R.CLAIM_IN_PROGRESS, R.DENIED], 1, 2, "rights_in_progress"),
        ([R.CLAIMED, R.DENIED, R.NOT_APPLICABLE], 3, 3, "rights_resolved"),
        ([], 3, 3, "rights_resolved"),
    ],
)
def test_ap7_alternatives_suggestion(statuses: list[R], low: int, high: int, code: str) -> None:
    s = suggest_alternatives(statuses, C)
    assert (s.low, s.high, s.reason.code) == (low, high, code)
