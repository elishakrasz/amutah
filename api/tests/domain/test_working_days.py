from datetime import UTC, date, datetime

import pytest

from app.domain.enums import Tier
from app.domain.working_days import (
    ISRAEL,
    add_working_days,
    is_working_day,
    sla_due,
    working_days_between,
)
from tests.domain.helpers import cfg

C = cfg()
SUKKOT = frozenset({date(2026, 10, 1)})  # synthetic holiday for the test


def test_friday_saturday_and_holidays_are_off() -> None:
    assert is_working_day(date(2026, 10, 18), frozenset())  # Sunday
    assert not is_working_day(date(2026, 10, 23), frozenset())  # Friday
    assert not is_working_day(date(2026, 10, 24), frozenset())  # Saturday
    assert not is_working_day(date(2026, 10, 1), SUKKOT)


def test_add_working_days() -> None:
    thursday = date(2026, 10, 22)
    assert add_working_days(thursday, 1, frozenset()) == date(2026, 10, 25)  # Sunday
    assert add_working_days(thursday, 0, frozenset()) == thursday
    assert add_working_days(date(2026, 9, 30), 1, SUKKOT) == date(2026, 10, 4)
    with pytest.raises(ValueError):
        add_working_days(thursday, -1, frozenset())


def test_working_days_between() -> None:
    assert working_days_between(date(2026, 10, 22), date(2026, 10, 27), frozenset()) == 3
    assert working_days_between(date(2026, 10, 22), date(2026, 10, 22), frozenset()) == 0
    with pytest.raises(ValueError):
        working_days_between(date(2026, 10, 22), date(2026, 10, 21), frozenset())


def test_tier_a_due_end_of_second_working_day_israel_time() -> None:
    # Thursday 23:30 in Israel is still Thursday locally (20:30 UTC).
    submitted = datetime(2026, 10, 22, 20, 30, tzinfo=UTC)
    due = sla_due(submitted, C.tier(Tier.A), frozenset())
    assert due == datetime(2026, 10, 27, 0, 0, tzinfo=ISRAEL)  # end of Monday


def test_emergency_due_in_hours() -> None:
    submitted = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)  # Friday
    assert sla_due(submitted, C.tier(Tier.E), frozenset()) == datetime(
        2026, 10, 24, 9, 0, tzinfo=UTC
    )


def test_sla_needs_aware_datetime() -> None:
    with pytest.raises(ValueError):
        sla_due(datetime(2026, 10, 22, 9, 0), C.tier(Tier.A), frozenset())


# --- Q20/Q21 SLA pauses and restarts

from datetime import timedelta  # noqa: E402

from app.domain.enums import SlaEventKind as K  # noqa: E402
from app.domain.working_days import SlaEvent, current_sla_due  # noqa: E402

SUN = datetime(2026, 10, 18, 7, 0, tzinfo=UTC)  # 10:00 Israel, Sunday


def due(tier: Tier, events: list[SlaEvent]) -> datetime | None:
    return current_sla_due(SUN, tier, events, dict(C.tiers), frozenset())


def test_no_events_is_the_plain_sla() -> None:
    assert due(Tier.B, []) == sla_due(SUN, C.tier(Tier.B), frozenset())


def test_q21_clock_stops_while_paused() -> None:
    assert due(Tier.B, [SlaEvent(SUN + timedelta(days=1), K.PAUSED)]) is None


def test_q21_pause_extends_by_the_working_days_it_spanned() -> None:
    plain = due(Tier.B, [])
    assert plain is not None
    # Paused Monday, resumed Wednesday: two working days.
    events = [
        SlaEvent(SUN + timedelta(days=1), K.PAUSED),
        SlaEvent(SUN + timedelta(days=3), K.RESUMED),
    ]
    extended = due(Tier.B, events)
    assert extended == datetime(2026, 10, 30, 0, 0, tzinfo=ISRAEL)  # end of Thursday 29th
    assert plain == datetime(2026, 10, 28, 0, 0, tzinfo=ISRAEL)


def test_pause_within_one_day_extends_nothing_for_working_day_slas() -> None:
    events = [SlaEvent(SUN, K.PAUSED), SlaEvent(SUN + timedelta(hours=2), K.RESUMED)]
    assert due(Tier.B, events) == due(Tier.B, [])


def test_hour_slas_extend_by_the_paused_time() -> None:
    events = [SlaEvent(SUN, K.PAUSED), SlaEvent(SUN + timedelta(hours=2), K.RESUMED)]
    assert due(Tier.E, events) == SUN + timedelta(hours=26)


def test_resume_without_pause_and_double_pause_are_harmless() -> None:
    events = [
        SlaEvent(SUN, K.RESUMED),
        SlaEvent(SUN + timedelta(days=1), K.PAUSED),
        SlaEvent(SUN + timedelta(days=2), K.PAUSED),
        SlaEvent(SUN + timedelta(days=3), K.RESUMED),
    ]
    # The second pause is ignored; the pause is Monday to Wednesday as above.
    assert due(Tier.B, events) == datetime(2026, 10, 30, 0, 0, tzinfo=ISRAEL)


def test_q20_escalation_restarts_on_the_tier_c_sla() -> None:
    escalated = SUN + timedelta(days=4)  # Thursday
    events = [
        SlaEvent(SUN + timedelta(days=1), K.PAUSED),
        SlaEvent(SUN + timedelta(days=2), K.RESUMED),  # dropped by the restart
        SlaEvent(escalated, K.RESTARTED, Tier.C),
    ]
    assert due(Tier.B, events) == sla_due(escalated, C.tier(Tier.C), frozenset())


def test_restart_while_paused_stays_paused() -> None:
    events = [
        SlaEvent(SUN, K.PAUSED),
        SlaEvent(SUN + timedelta(days=1), K.RESTARTED, Tier.C),
    ]
    assert due(Tier.B, events) is None
    resumed = [*events, SlaEvent(SUN + timedelta(days=2), K.RESUMED)]
    assert due(Tier.B, resumed) is not None


def test_restart_needs_a_tier() -> None:
    with pytest.raises(ValueError):
        due(Tier.B, [SlaEvent(SUN, K.RESTARTED)])
