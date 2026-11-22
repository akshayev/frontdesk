"""U-1 … U-9: working-time calendar (SLA-3, SLA-4). Inputs are built in IST with ZoneInfo.

Reference week: Mon 23 Nov 2026 … Fri 27 Nov 2026; Sat 28 / Sun 29; Mon 30 Nov.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.sla.calendar import add_working_minutes, working_minutes_between
from app.sla.policy import TARGETS, Priority

IST = ZoneInfo("Asia/Kolkata")
NO_HOLIDAYS: frozenset[date] = frozenset()
XMAS = frozenset({date(2026, 12, 25)})


def ist(y: int, mo: int, d: int, h: int, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=IST)


def test_u1_urgent_friday_1800_due_monday_1100() -> None:
    """U-1 / SLA-4: urgent created Fri 18:00 → response due Mon 11:00 (30 Fri + 90 Mon)."""
    created = ist(2026, 11, 27, 18, 0)
    response_min = TARGETS[Priority.urgent][0]
    assert response_min == 120
    assert add_working_minutes(created, response_min, NO_HOLIDAYS) == ist(2026, 11, 30, 11, 0)


def test_u2_created_saturday_counts_from_monday_opening() -> None:
    """U-2: created Sat 10:00, 60 min → Mon 10:30."""
    assert add_working_minutes(ist(2026, 11, 28, 10), 60, NO_HOLIDAYS) == ist(2026, 11, 30, 10, 30)


def test_u3_created_before_opening() -> None:
    """U-3: created Tue 08:00, 30 min → Tue 10:00."""
    assert add_working_minutes(ist(2026, 11, 24, 8), 30, NO_HOLIDAYS) == ist(2026, 11, 24, 10, 0)


def test_u4_created_exactly_at_closing() -> None:
    """U-4: created Wed 18:30 exactly, 1 min → Thu 09:31 (18:30 is outside working time)."""
    assert add_working_minutes(ist(2026, 11, 25, 18, 30), 1, NO_HOLIDAYS) == ist(
        2026, 11, 26, 9, 31
    )


def test_u5_holiday_is_skipped() -> None:
    """U-5: holiday Fri 25 Dec 2026; created Thu 24 Dec 18:00, 60 min → Mon 28 Dec 10:00."""
    assert add_working_minutes(ist(2026, 12, 24, 18), 60, XMAS) == ist(2026, 12, 28, 10, 0)


def test_u6_between_over_weekend() -> None:
    """U-6: Fri 17:30 → Mon 10:30 = 60 + 60 = 120 working minutes."""
    assert working_minutes_between(ist(2026, 11, 27, 17, 30), ist(2026, 11, 30, 10, 30),
                                   NO_HOLIDAYS) == 120


def test_u7_between_reversed_is_negative() -> None:
    """U-7: reversed arguments give the negated value."""
    assert working_minutes_between(ist(2026, 11, 30, 10, 30), ist(2026, 11, 27, 17, 30),
                                   NO_HOLIDAYS) == -120


def test_u8_medium_resolution_from_monday_opening() -> None:
    """U-8: medium resolution 1620 from Mon 09:30 → Wed 18:30 (ends at closing, same day)."""
    resolution_min = TARGETS[Priority.medium][1]
    assert resolution_min == 1620
    assert add_working_minutes(ist(2026, 11, 23, 9, 30), resolution_min, NO_HOLIDAYS) == ist(
        2026, 11, 25, 18, 30
    )


def test_u9_low_resolution_from_monday_opening() -> None:
    """U-9: low resolution 2700 from Mon 09:30 → Fri 18:30."""
    resolution_min = TARGETS[Priority.low][1]
    assert resolution_min == 2700
    assert add_working_minutes(ist(2026, 11, 23, 9, 30), resolution_min, NO_HOLIDAYS) == ist(
        2026, 11, 27, 18, 30
    )


# --- contract details (ARCHITECTURE §5) -------------------------------------------------


def test_naive_datetimes_are_rejected() -> None:
    naive = datetime(2026, 11, 23, 10, 0)
    with pytest.raises(ValueError):
        add_working_minutes(naive, 10, NO_HOLIDAYS)
    with pytest.raises(ValueError):
        working_minutes_between(naive, ist(2026, 11, 23, 11), NO_HOLIDAYS)
    with pytest.raises(ValueError):
        working_minutes_between(ist(2026, 11, 23, 11), naive, NO_HOLIDAYS)


def test_result_is_utc_aware() -> None:
    result = add_working_minutes(ist(2026, 11, 23, 10), 30, NO_HOLIDAYS)
    assert result.tzinfo is UTC
    assert result == datetime(2026, 11, 23, 5, 0, tzinfo=UTC)  # 10:30 IST


def test_utc_input_is_interpreted_in_ist() -> None:
    """04:00 UTC = 09:30 IST Monday: counting starts immediately."""
    start = datetime(2026, 11, 23, 4, 0, tzinfo=UTC)
    assert add_working_minutes(start, 60, NO_HOLIDAYS) == ist(2026, 11, 23, 10, 30)


def test_zero_minutes_from_outside_working_time_is_next_opening() -> None:
    assert add_working_minutes(ist(2026, 11, 28, 12), 0, NO_HOLIDAYS) == ist(2026, 11, 30, 9, 30)
    assert add_working_minutes(ist(2026, 11, 23, 12), 0, NO_HOLIDAYS) == ist(2026, 11, 23, 12)


def test_full_day_inside_working_time_ends_at_closing() -> None:
    assert add_working_minutes(ist(2026, 11, 23, 9, 30), 540, NO_HOLIDAYS) == ist(
        2026, 11, 23, 18, 30
    )
    assert add_working_minutes(ist(2026, 11, 23, 9, 30), 541, NO_HOLIDAYS) == ist(
        2026, 11, 24, 9, 31
    )


def test_negative_minutes_count_backwards() -> None:
    """Negative minutes: inverse of the forward count."""
    assert add_working_minutes(ist(2026, 11, 30, 11, 0), -120, NO_HOLIDAYS) == ist(
        2026, 11, 27, 18, 0
    )
    # from outside working time: start at the previous closing
    assert add_working_minutes(ist(2026, 11, 28, 12), -30, NO_HOLIDAYS) == ist(
        2026, 11, 27, 18, 0
    )
    assert add_working_minutes(ist(2026, 12, 28, 10), -60, XMAS) == ist(2026, 12, 24, 18, 0)
    # ending exactly on a day boundary reports the earlier 18:30 (same as forward counting)
    assert add_working_minutes(ist(2026, 11, 24, 10), -30, NO_HOLIDAYS) == ist(2026, 11, 23, 18, 30)
    assert add_working_minutes(ist(2026, 11, 25, 9, 30), -540, NO_HOLIDAYS) == ist(
        2026, 11, 23, 18, 30
    )


def test_between_outside_working_time_is_zero() -> None:
    assert working_minutes_between(ist(2026, 11, 28, 9), ist(2026, 11, 29, 20), NO_HOLIDAYS) == 0
    assert working_minutes_between(ist(2026, 11, 23, 19), ist(2026, 11, 24, 9), NO_HOLIDAYS) == 0


def test_between_truncates_partial_minutes_toward_zero() -> None:
    a = ist(2026, 11, 23, 10, 0, 0)
    b = ist(2026, 11, 23, 10, 1, 59)
    assert working_minutes_between(a, b, NO_HOLIDAYS) == 1
    assert working_minutes_between(b, a, NO_HOLIDAYS) == -1


def test_between_and_add_are_consistent() -> None:
    start = ist(2026, 12, 23, 14, 17)
    for minutes in (0, 1, 59, 540, 1000, 2700, 5000):
        end = add_working_minutes(start, minutes, XMAS)
        assert working_minutes_between(start, end, XMAS) == minutes


def test_holiday_on_weekday_counts_zero() -> None:
    assert working_minutes_between(ist(2026, 12, 25, 9), ist(2026, 12, 25, 19), XMAS) == 0
    assert working_minutes_between(
        ist(2026, 12, 24, 9, 30), ist(2026, 12, 24, 9, 30) + timedelta(days=4), XMAS
    ) == 540  # only Thu 24 counts: Fri 25 holiday, weekend, Mon 28 ends at 09:30
