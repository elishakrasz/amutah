from datetime import UTC, datetime, timedelta

import pytest

from app.domain.budget import QueueItem, budget_status, emergency_only, order_queue
from app.domain.enums import Tier
from tests.domain.helpers import MONTHLY_BUDGET, cfg

C = cfg()
T0 = datetime(2026, 10, 19, tzinfo=UTC)


def test_status_and_reserve() -> None:
    s = budget_status(paid=1_000_000, committed=1_000_000, pending_bc=500_000, cfg=C)
    assert (s.remaining, s.reserve, s.available_for_general) == (4_000_000, 1_000_000, 3_000_000)
    assert not s.constrained
    tight = budget_status(paid=1_000_000, committed=2_500_000, pending_bc=600_000, cfg=C)
    assert tight.constrained


def test_ap20_emergency_only_threshold() -> None:
    assert not emergency_only(budget_status(4_500_000, 0, 0, C), C)  # exactly 10% left
    assert emergency_only(budget_status(4_500_001, 0, 0, C), C)


def test_budget_needs_board_allocation() -> None:
    with pytest.raises(ValueError, match="board"):
        budget_status(0, 0, 0, cfg(**{"budget.monthly_allocation": None}))
    assert MONTHLY_BUDGET == 5_000_000


ITEMS = [
    QueueItem("late-high", Tier.B, 11, False, T0 + timedelta(days=5)),
    QueueItem("soon-low", Tier.B, 4, False, T0 + timedelta(days=1)),
    QueueItem("urgent-mid", Tier.C, 8, True, T0 + timedelta(days=9)),
    QueueItem("calm-mid", Tier.C, 8, False, T0 + timedelta(days=3)),
    QueueItem("emergency", Tier.E, None, True, T0 + timedelta(days=2)),
    QueueItem("unscored", Tier.B, None, False, T0),
]


def test_normal_queue_is_by_due_time() -> None:
    order = order_queue(ITEMS, constrained=False)
    assert [e.item.case_id for e in order][:2] == ["unscored", "soon-low"]
    assert not any(e.waiting_for_budget for e in order)


def test_ap20_constrained_queue_is_by_score_then_urgency() -> None:
    order = order_queue(ITEMS, constrained=True)
    assert [e.item.case_id for e in order] == [
        "emergency",
        "late-high",
        "urgent-mid",
        "calm-mid",
        "soon-low",
        "unscored",
    ]
    assert [e.waiting_for_budget for e in order] == [False, True, True, True, True, True]
