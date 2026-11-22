"""U-10 … U-21: SLA policy (PRI-*, WAIT-*, RO-*, SLA-7, SLA-8, D-024, D-025).

Reference week: Mon 23 Nov 2026 … Fri 27 Nov 2026; Sat 28 / Sun 29; Mon 30 Nov.
"""

from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.sla.calendar import add_working_minutes, working_minutes_between
from app.sla.policy import (
    TARGETS,
    Badge,
    Clock,
    Priority,
    badge,
    can_reopen,
    change_priority,
    initial_clock,
    pause,
    resolve,
    resume,
    should_auto_close,
    target_statuses,
)

IST = ZoneInfo("Asia/Kolkata")
H: frozenset[date] = frozenset()


def ist(y: int, mo: int, d: int, h: int, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=IST)


def replied(clock: Clock, at: datetime) -> Clock:
    """SLA-5: the first public agent reply meets the response target."""
    return replace(clock, first_response_at=at)


# --- priority change (PRI-1 … PRI-4, D-024) ---------------------------------------------


def test_u10_upgrade_takes_earlier_new_due() -> None:
    """U-10 / PRI-1 / D-008: medium created Mon 10:00 (due 14:30) → urgent at 10:30 → 12:30."""
    clock = initial_clock(Priority.medium, ist(2026, 11, 23, 10), H)
    assert clock.first_response_due_at == ist(2026, 11, 23, 14, 30)
    changed = change_priority(clock, Priority.urgent, ist(2026, 11, 23, 10, 30), H)
    assert changed.priority is Priority.urgent
    assert changed.first_response_due_at == ist(2026, 11, 23, 12, 30)


def test_u11_upgrade_never_extends_due() -> None:
    """U-11 / PRI-1: → urgent at 13:00 would give 15:00, so the due stays 14:30."""
    clock = initial_clock(Priority.medium, ist(2026, 11, 23, 10), H)
    changed = change_priority(clock, Priority.urgent, ist(2026, 11, 23, 13), H)
    assert changed.first_response_due_at == ist(2026, 11, 23, 14, 30)


def test_u12_downgrade_is_created_plus_new_target() -> None:
    """U-12 / PRI-2 / D-024: urgent → low: due = created + 540 working min (low response)."""
    created = ist(2026, 11, 23, 10)
    clock = initial_clock(Priority.urgent, created, H)
    changed = change_priority(clock, Priority.low, ist(2026, 11, 23, 11), H)
    assert changed.first_response_due_at == add_working_minutes(created, 540, H)
    assert changed.first_response_due_at == ist(2026, 11, 24, 10, 0)
    assert changed.resolution_due_at == add_working_minutes(created, 2700, H)


def test_u12_downgrade_when_overdue_still_created_plus_new_target() -> None:
    """U-12 / D-024 with a negative remaining (already overdue): still created + new target."""
    created = ist(2026, 11, 23, 9, 30)
    clock = initial_clock(Priority.urgent, created, H)
    now = ist(2026, 11, 25, 9, 30)  # response (due Mon 11:30) is 2 working days overdue
    changed = change_priority(clock, Priority.low, now, H)
    assert changed.first_response_due_at == add_working_minutes(created, 540, H)
    assert changed.first_response_due_at == ist(2026, 11, 23, 18, 30)
    assert badge(changed, now, H) == Badge("late", "response", 540)


def test_u13_met_response_is_not_recalculated() -> None:
    """U-13 / PRI-3: response already met → unchanged; the unmet resolution still changes."""
    clock = replied(initial_clock(Priority.medium, ist(2026, 11, 23, 10), H),
                    ist(2026, 11, 23, 10, 15))
    now = ist(2026, 11, 23, 10, 30)
    changed = change_priority(clock, Priority.urgent, now, H)
    assert changed.first_response_due_at == clock.first_response_due_at
    assert changed.first_response_at == clock.first_response_at
    assert changed.resolution_due_at == add_working_minutes(now, 540, H)  # earlier than medium


def test_u13_resolved_ticket_resolution_is_not_recalculated() -> None:
    """PRI-3 for the resolution target."""
    clock = replied(initial_clock(Priority.medium, ist(2026, 11, 23, 10), H), ist(2026, 11, 23, 11))
    done = resolve(clock, ist(2026, 11, 23, 15), H)
    changed = change_priority(done, Priority.urgent, ist(2026, 11, 23, 16), H)
    assert changed.resolution_due_at == done.resolution_due_at
    assert changed.resolved_at == done.resolved_at


def _paused_medium() -> Clock:
    """Medium created Mon 09:30 (resolution due Wed 18:30), replied 09:45, paused Mon 10:30."""
    clock = replied(initial_clock(Priority.medium, ist(2026, 11, 23, 9, 30), H),
                    ist(2026, 11, 23, 9, 45))
    paused = pause(clock, ist(2026, 11, 23, 10, 30), H)
    assert paused.resolution_remaining_min == 1560
    return paused


def test_u14_upgrade_while_paused_caps_remaining() -> None:
    """U-14 / PRI-4: upgrade → remaining = min(remaining, new target) = min(1560, 540)."""
    paused = _paused_medium()
    changed = change_priority(paused, Priority.urgent, ist(2026, 11, 24, 12), H)
    assert changed.resolution_remaining_min == 540
    assert changed.paused_at == paused.paused_at
    assert changed.resolution_due_at == paused.resolution_due_at  # due recomputed on resume


def test_u14_downgrade_while_paused_uses_d024_formula() -> None:
    """U-14 / PRI-4 / D-024: downgrade → remaining = 2700 − (1620 − 1560) = 2640."""
    paused = _paused_medium()
    changed = change_priority(paused, Priority.low, ist(2026, 11, 24, 12), H)
    assert changed.resolution_remaining_min == 2640
    resumed = resume(changed, ist(2026, 11, 25, 9, 30), H)
    assert resumed.resolution_due_at == add_working_minutes(ist(2026, 11, 25, 9, 30), 2640, H)


def test_u14_downgrade_while_paused_and_overdue_keeps_breach_consistent() -> None:
    """D-024 on a breach-preserved pause: a result still ≤ 0 moves the due, stays late."""
    clock = replied(initial_clock(Priority.urgent, ist(2026, 11, 23, 9, 30), H),
                    ist(2026, 11, 23, 9, 40))
    # urgent resolution due Mon 18:30; paused Fri 09:30 → Tue+Wed+Thu = 1620 overdue
    paused = pause(clock, ist(2026, 11, 27, 9, 30), H)
    assert badge(paused, ist(2026, 11, 27, 12), H) == Badge("late", "resolution", 1620)
    changed = change_priority(paused, Priority.medium, ist(2026, 11, 27, 12), H)
    # 1620 − (540 − (−1620)) = −540 → due = created + 1620 = Wed 18:30, still late by 540
    assert changed.resolution_remaining_min == 0
    assert changed.resolution_due_at == ist(2026, 11, 25, 18, 30)
    assert badge(changed, ist(2026, 11, 27, 15), H) == Badge("late", "resolution", 540)
    # resume keeps the (moved) preserved due: WAIT-3
    assert resume(changed, ist(2026, 11, 30, 10), H).resolution_due_at == ist(2026, 11, 25, 18, 30)


# --- pause / resume (WAIT-3, RO-1, D-013) -----------------------------------------------


def test_u15_pause_resume_preserves_remaining() -> None:
    """U-15 / WAIT-3: 1560 left at pause; resume Tue 10:30 → due = Tue 10:30 + 1560 = Thu 18:30."""
    paused = _paused_medium()
    resumed = resume(paused, ist(2026, 11, 24, 10, 30), H)
    assert resumed.resolution_due_at == ist(2026, 11, 26, 18, 30)
    assert resumed.paused_at is None and resumed.resolution_remaining_min is None
    assert working_minutes_between(ist(2026, 11, 24, 10, 30), resumed.resolution_due_at, H) == 1560


def test_u16_pause_when_overdue_keeps_old_due() -> None:
    """U-16 / WAIT-3: overdue at pause → remaining 0, old due kept on pause AND on resume."""
    clock = replied(initial_clock(Priority.urgent, ist(2026, 11, 23, 9, 30), H),
                    ist(2026, 11, 23, 9, 40))
    old_due = clock.resolution_due_at
    assert old_due == ist(2026, 11, 23, 18, 30)
    paused = pause(clock, ist(2026, 11, 24, 10), H)
    assert paused.resolution_remaining_min == 0
    assert paused.resolution_due_at == old_due
    resumed = resume(paused, ist(2026, 11, 25, 10), H)
    assert resumed.resolution_due_at == old_due


def test_resolve_then_reopen_resumes_with_remaining() -> None:
    """RO-1 / D-013: reopen resumes with the minutes that were left at resolve time."""
    clock = replied(initial_clock(Priority.medium, ist(2026, 11, 23, 9, 30), H),
                    ist(2026, 11, 23, 9, 45))
    done = resolve(clock, ist(2026, 11, 23, 10, 30), H)
    assert done.resolution_remaining_min == 1560
    assert badge(done, ist(2026, 11, 24, 10), H).state == "met"
    reopened = resume(done, ist(2026, 11, 26, 9, 30), H)
    assert reopened.resolved_at is None
    assert reopened.resolution_due_at == add_working_minutes(ist(2026, 11, 26, 9, 30), 1560, H)


def test_illegal_clock_operations_raise() -> None:
    clock = initial_clock(Priority.low, ist(2026, 11, 23, 10), H)
    with pytest.raises(ValueError):
        resume(clock, ist(2026, 11, 23, 11), H)
    paused = pause(clock, ist(2026, 11, 23, 11), H)
    with pytest.raises(ValueError):
        pause(paused, ist(2026, 11, 23, 12), H)
    with pytest.raises(ValueError):
        resolve(paused, ist(2026, 11, 23, 12), H)


# --- badge (SLA-7, SLA-8, D-025) --------------------------------------------------------


def test_u17_at_risk_threshold_is_strictly_below_25_percent() -> None:
    """U-17 / SLA-8: urgent response 120 → at risk when < 30 working minutes remain."""
    clock = initial_clock(Priority.urgent, ist(2026, 11, 23, 9, 30), H)  # response due 11:30
    assert badge(clock, ist(2026, 11, 23, 11, 0), H) == Badge("on_track", "response", 30)
    assert badge(clock, ist(2026, 11, 23, 11, 1), H) == Badge("at_risk", "response", 29)


def test_u17_at_risk_resolution_after_response_met() -> None:
    """U-17: urgent resolution 540 → at risk below 135 minutes left."""
    clock = replied(initial_clock(Priority.urgent, ist(2026, 11, 23, 9, 30), H),
                    ist(2026, 11, 23, 9, 45))  # resolution due 18:30
    assert badge(clock, ist(2026, 11, 23, 16, 15), H) == Badge("on_track", "resolution", 135)
    assert badge(clock, ist(2026, 11, 23, 16, 16), H) == Badge("at_risk", "resolution", 134)


def test_u18_late_when_unmet_past_due() -> None:
    """U-18 / SLA-7: unmet and now > due → late, minutes overdue."""
    clock = initial_clock(Priority.urgent, ist(2026, 11, 23, 9, 30), H)
    assert badge(clock, ist(2026, 11, 23, 11, 45), H) == Badge("late", "response", 15)


def test_u18_met() -> None:
    """U-18 / SLA-6: both targets met on time → met (resolution), minutes to spare."""
    clock = replied(initial_clock(Priority.urgent, ist(2026, 11, 23, 9, 30), H),
                    ist(2026, 11, 23, 10))
    done = resolve(clock, ist(2026, 11, 23, 17, 30), H)
    assert badge(done, ist(2026, 11, 24, 10), H) == Badge("met", "resolution", 60)


def test_u18_paused() -> None:
    """U-18 / WAIT-1: waiting on customer with time left → paused, minutes left frozen."""
    paused = _paused_medium()
    assert badge(paused, ist(2026, 11, 26, 15), H) == Badge("paused", "resolution", 1560)


def test_u18_late_is_sticky_for_missed_response() -> None:
    """U-18 / D-025: response replied 30 min late → badge stays late (response, 30)."""
    clock = replied(initial_clock(Priority.urgent, ist(2026, 11, 23, 9, 30), H),
                    ist(2026, 11, 23, 12, 0))
    now = ist(2026, 11, 23, 13, 0)
    assert badge(clock, now, H) == Badge("late", "response", 30)
    response, resolution = target_statuses(clock, now, H)
    assert (response.state, response.minutes) == ("late", 30)
    assert response.met_at == clock.first_response_at
    assert (resolution.state, resolution.minutes) == ("on_track", 330)  # panel still counts down


def test_u18_both_missed_shows_resolution() -> None:
    """D-025: both targets missed → resolution is shown."""
    clock = replied(initial_clock(Priority.urgent, ist(2026, 11, 23, 9, 30), H),
                    ist(2026, 11, 23, 12, 0))
    done = resolve(clock, ist(2026, 11, 24, 10, 30), H)  # due Mon 18:30 → 60 late
    assert badge(done, ist(2026, 11, 24, 11), H) == Badge("late", "resolution", 60)


def test_sla4_not_late_over_the_weekend() -> None:
    """SLA-4: urgent created Fri 18:00 must not show late on Sat/Sun."""
    clock = initial_clock(Priority.urgent, ist(2026, 11, 27, 18), H)
    for now in (ist(2026, 11, 28, 12), ist(2026, 11, 29, 23, 59)):
        assert badge(clock, now, H) == Badge("on_track", "response", 90)
    assert badge(clock, ist(2026, 11, 30, 11, 1), H) == Badge("late", "response", 1)


def test_u21_overdue_minutes_freeze_while_paused() -> None:
    """U-21 / D-025: overdue by 30 at pause → still late by 30 after 2 working days paused."""
    clock = replied(initial_clock(Priority.urgent, ist(2026, 11, 23, 9, 30), H),
                    ist(2026, 11, 23, 9, 40))  # resolution due Mon 18:30
    paused = pause(clock, ist(2026, 11, 24, 10, 0), H)  # 30 working min overdue
    assert badge(paused, ist(2026, 11, 24, 10, 0), H) == Badge("late", "resolution", 30)
    assert badge(paused, ist(2026, 11, 26, 10, 0), H) == Badge("late", "resolution", 30)


# --- auto-close and reopen window (WAIT-4, RO-1, RO-3, D-025 boundary) ------------------


def test_u19_auto_close_after_five_working_days() -> None:
    """U-19 / WAIT-4: paused Mon 10:00 → boundary next Mon 10:00 (2700 working min, >=)."""
    paused_at = ist(2026, 11, 23, 10)
    assert not should_auto_close(paused_at, ist(2026, 11, 28, 12), H)  # Saturday
    assert not should_auto_close(paused_at, ist(2026, 11, 30, 9, 59), H)
    assert should_auto_close(paused_at, ist(2026, 11, 30, 10, 0), H)  # exactly 2700
    assert should_auto_close(paused_at, ist(2026, 11, 30, 10, 1), H)


def test_u19_auto_close_respects_holidays() -> None:
    xmas = frozenset({date(2026, 12, 25)})
    paused_at = ist(2026, 12, 21, 10)  # Mon; Fri 25 is a holiday → boundary Tue 29 10:00
    assert not should_auto_close(paused_at, ist(2026, 12, 28, 10), xmas)
    assert should_auto_close(paused_at, ist(2026, 12, 29, 10), xmas)


def test_u20_reopen_window_seven_calendar_days() -> None:
    """U-20 / RO-1 / RO-3: allowed at 6d23h, refused at exactly 7d (D-025) and at 7d+1s."""
    resolved_at = ist(2026, 11, 23, 10)
    assert can_reopen(resolved_at, resolved_at + timedelta(days=6, hours=23))
    assert can_reopen(resolved_at, resolved_at + timedelta(days=7) - timedelta(microseconds=1))
    assert not can_reopen(resolved_at, resolved_at + timedelta(days=7))
    assert not can_reopen(resolved_at, resolved_at + timedelta(days=7, seconds=1))


def test_can_reopen_rejects_naive() -> None:
    with pytest.raises(ValueError):
        can_reopen(datetime(2026, 11, 23, 10), ist(2026, 11, 24, 10))


@pytest.mark.parametrize(
    ("old", "new"),
    [(Priority.urgent, Priority.medium), (Priority.urgent, Priority.low),
     (Priority.medium, Priority.low)],
)
def test_d024_downgrade_equals_created_plus_new_target(old: Priority, new: Priority) -> None:
    """D-024: for any change time (on time, overdue, weekend) the downgraded due equals
    created_at + new target in working time (exactly the same instant)."""
    xmas = frozenset({date(2026, 12, 25)})
    for created in (ist(2026, 12, 21, 9, 30), ist(2026, 12, 23, 17, 47), ist(2026, 12, 26, 11)):
        clock = initial_clock(old, created, xmas)
        for hours in range(0, 24 * 14, 5):
            now = created + timedelta(hours=hours, minutes=7)
            changed = change_priority(clock, new, now, xmas)
            resp, res = (add_working_minutes(created, m, xmas) for m in TARGETS[new])
            assert changed.first_response_due_at == resp, (created, now)
            assert changed.resolution_due_at == res, (created, now)
