"""Working-time maths. Implements: SLA-3, SLA-4.

Working time is 09:30–18:30 Asia/Kolkata, Monday–Friday, minus the dates in `holidays`
(IST calendar dates). The working interval of a day is half-open [09:30, 18:30): an instant
at exactly 18:30 is outside working time, so counting from it starts at the next opening.

Pure module: no FastAPI, no SQLAlchemy, no clock (test A-2). Every instant passed in must be
timezone-aware; every instant returned is UTC-aware.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Kolkata")
OPEN = time(9, 30)
CLOSE = time(18, 30)
WORKING_MINUTES_PER_DAY = 540
_MINUTE = timedelta(minutes=1)

Holidays = frozenset[date]


def _require_aware(value: datetime, name: str) -> None:
    """Reject naive datetimes: a naive value has no defined instant (SLA-3)."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware, got naive {value!r}")


def is_working_day(day: date, holidays: Holidays) -> bool:
    """SLA-3: Monday–Friday and not a holiday."""
    return day.weekday() < 5 and day not in holidays


def _opening(day: date) -> datetime:
    return datetime.combine(day, OPEN, tzinfo=TZ)


def _closing(day: date) -> datetime:
    return datetime.combine(day, CLOSE, tzinfo=TZ)


def _next_working_day(day: date, holidays: Holidays) -> date:
    day += timedelta(days=1)
    while not is_working_day(day, holidays):
        day += timedelta(days=1)
    return day


def _previous_working_day(day: date, holidays: Holidays) -> date:
    day -= timedelta(days=1)
    while not is_working_day(day, holidays):
        day -= timedelta(days=1)
    return day


def _forward_start(t: datetime, holidays: Holidays) -> datetime:
    """The instant `t` if it is working time, else the next opening (SLA-4)."""
    day = t.date()
    if is_working_day(day, holidays):
        if t < _opening(day):
            return _opening(day)
        if t < _closing(day):
            return t
    return _opening(_next_working_day(day, holidays))


def _backward_start(t: datetime, holidays: Holidays) -> datetime:
    """Mirror of _forward_start for counting backwards: `t` if inside (open, close], else
    the previous closing."""
    day = t.date()
    if is_working_day(day, holidays):
        if t > _closing(day):
            return _closing(day)
        if t > _opening(day):
            return t
    return _closing(_previous_working_day(day, holidays))


def add_working_minutes(start: datetime, minutes: int, holidays: Holidays) -> datetime:
    """Return the instant `minutes` working minutes after `start` (SLA-3, SLA-4).

    If `start` is outside working time, counting begins at the next working opening
    (Fri 18:00 + 120 → Mon 11:00). A target that ends exactly at closing time returns 18:30
    of that day, not 09:30 of the next.

    Negative `minutes` count backwards (from the previous closing if `start` is outside
    working time; a day boundary is reported as 18:30, never 09:30): the inverse of the
    forward count.
    """
    _require_aware(start, "start")
    t = start.astimezone(TZ)
    if minutes >= 0:
        result = _add_forward(t, timedelta(minutes=minutes), holidays)
    else:
        result = _add_backward(t, timedelta(minutes=-minutes), holidays)
    return result.astimezone(UTC)


def _add_forward(t: datetime, remaining: timedelta, holidays: Holidays) -> datetime:
    t = _forward_start(t, holidays)
    while True:
        available = _closing(t.date()) - t
        if remaining <= available:
            return t + remaining
        remaining -= available
        t = _opening(_next_working_day(t.date(), holidays))


def _add_backward(t: datetime, remaining: timedelta, holidays: Holidays) -> datetime:
    """Same boundary convention as forward: a count ending exactly on a day boundary is
    reported as the earlier day's 18:30, never the later day's 09:30."""
    t = _backward_start(t, holidays)
    while True:
        available = t - _opening(t.date())
        if remaining < available:
            return t - remaining
        remaining -= available
        t = _closing(_previous_working_day(t.date(), holidays))
        if not remaining:
            return t


def working_minutes_between(a: datetime, b: datetime, holidays: Holidays) -> int:
    """Whole working minutes from `a` to `b` (SLA-3); negative if b < a (U-7).

    Partial minutes are truncated toward zero, so the result is antisymmetric:
    working_minutes_between(a, b) == -working_minutes_between(b, a).
    """
    _require_aware(a, "a")
    _require_aware(b, "b")
    if b < a:
        return -working_minutes_between(b, a, holidays)
    start, end = a.astimezone(TZ), b.astimezone(TZ)
    total = timedelta(0)
    day = start.date()
    while day <= end.date():
        if is_working_day(day, holidays):
            lo = max(start, _opening(day))
            hi = min(end, _closing(day))
            if hi > lo:
                total += hi - lo
        day += timedelta(days=1)
    return total // _MINUTE
