"""Working days (no Friday, Saturday or Israeli public holiday) and SLA due
times. Holidays come from the holiday table, never from a library guess."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.config import TierRule
from app.domain.enums import SlaEventKind, Tier

ISRAEL = ZoneInfo("Asia/Jerusalem")
FRIDAY, SATURDAY = 4, 5


def is_working_day(day: date, holidays: frozenset[date]) -> bool:
    return day.weekday() not in (FRIDAY, SATURDAY) and day not in holidays


def add_working_days(start: date, n: int, holidays: frozenset[date]) -> date:
    """The n-th working day after start (start itself does not count)."""
    if n < 0:
        raise ValueError("n must be non-negative")
    day = start
    while n:
        day += timedelta(days=1)
        if is_working_day(day, holidays):
            n -= 1
    return day


def working_days_between(start: date, end: date, holidays: frozenset[date]) -> int:
    """Working days after start up to and including end."""
    if end < start:
        raise ValueError("end before start")
    return sum(
        1
        for i in range(1, (end - start).days + 1)
        if is_working_day(start + timedelta(days=i), holidays)
    )


def sla_due(
    submitted_at: datetime,
    rule: TierRule,
    holidays: frozenset[date],
    paused: timedelta = timedelta(0),
    paused_working_days: int = 0,
) -> datetime:
    """When the decision is due, as an aware datetime. For working-day SLAs
    the case is due by the end of the n-th working day (Israel time) after
    submission. Pauses extend the deadline."""
    if submitted_at.tzinfo is None:
        raise ValueError("submitted_at must be timezone-aware")
    if rule.sla_hours is not None:
        return submitted_at + timedelta(hours=rule.sla_hours) + paused
    assert rule.sla_working_days is not None  # parse_config guarantees one is set
    local_day = submitted_at.astimezone(ISRAEL).date()
    due_day = add_working_days(local_day, rule.sla_working_days + paused_working_days, holidays)
    return datetime.combine(due_day + timedelta(days=1), time.min, tzinfo=ISRAEL)


@dataclass(frozen=True)
class SlaEvent:
    at: datetime
    kind: SlaEventKind
    tier: Tier | None = None  # for RESTARTED: the tier whose SLA now applies


def current_sla_due(
    submitted_at: datetime,
    tier: Tier,
    events: Sequence[SlaEvent],
    tiers: dict[Tier, TierRule],
    holidays: frozenset[date],
) -> datetime | None:
    """Due time after pauses (no alternate available, Q21) and restarts
    (escalation, Q20). None while the clock is paused. A paused working-day
    SLA is extended by the working days the pause spanned, counted in Israel
    dates; a pause that starts and ends on the same day extends nothing."""
    start, rule = submitted_at, tiers[tier]
    pauses: list[tuple[datetime, datetime]] = []
    paused_at: datetime | None = None
    for e in sorted(events, key=lambda e: e.at):
        if e.kind is SlaEventKind.RESTARTED:
            if e.tier is None:
                raise ValueError("a restart names the new tier")
            start, rule, pauses = e.at, tiers[e.tier], []
            paused_at = e.at if paused_at is not None else None
        elif e.kind is SlaEventKind.PAUSED:
            paused_at = paused_at or e.at
        elif paused_at is not None:  # RESUMED
            pauses.append((paused_at, e.at))
            paused_at = None
    if paused_at is not None:
        return None
    return sla_due(
        start,
        rule,
        holidays,
        paused=sum((end - begin for begin, end in pauses), timedelta(0)),
        paused_working_days=sum(
            working_days_between(
                begin.astimezone(ISRAEL).date(), end.astimezone(ISRAEL).date(), holidays
            )
            for begin, end in pauses
        ),
    )
