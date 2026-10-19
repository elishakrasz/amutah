"""AP-20 budget exhaustion. When the month's money cannot cover what is
committed and pending, the committee queue is ordered by score and urgency
and shows 'waiting for budget'. Tier E draws on the reserve."""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.domain.config import RulesConfig
from app.domain.enums import Tier


@dataclass(frozen=True)
class BudgetStatus:
    allocation: int
    paid: int
    committed: int  # approved, not yet paid
    pending: int  # requested amounts of tier B/C cases awaiting decision
    reserve: int

    @property
    def remaining(self) -> int:
        return self.allocation - self.paid

    @property
    def available_for_general(self) -> int:
        return self.remaining - self.reserve

    @property
    def constrained(self) -> bool:
        return self.available_for_general < self.committed + self.pending


def budget_status(paid: int, committed: int, pending_bc: int, cfg: RulesConfig) -> BudgetStatus:
    allocation = cfg.budget.monthly_allocation
    if allocation is None:
        raise ValueError("budget.monthly_allocation is not set (board decision)")
    return BudgetStatus(
        allocation=allocation,
        paid=paid,
        committed=committed,
        pending=pending_bc,
        reserve=allocation * cfg.budget.reserve_percent // 100,
    )


def emergency_only(status: BudgetStatus, cfg: RulesConfig) -> bool:
    """Below this the board is notified (AP-20)."""
    return status.remaining * 100 < status.allocation * cfg.budget.emergency_only_threshold_percent


@dataclass(frozen=True)
class QueueItem:
    case_id: Hashable
    tier: Tier
    score: int | None
    urgency: bool
    due: datetime


@dataclass(frozen=True)
class QueueEntry:
    item: QueueItem
    waiting_for_budget: bool


def order_queue(items: Sequence[QueueItem], constrained: bool) -> list[QueueEntry]:
    if not constrained:
        return [QueueEntry(i, False) for i in sorted(items, key=lambda i: i.due)]
    ranked = sorted(
        items,
        key=lambda i: (
            i.tier is not Tier.E,
            -(i.score if i.score is not None else -1),
            not i.urgency,
            i.due,
        ),
    )
    return [QueueEntry(i, i.tier is not Tier.E) for i in ranked]
