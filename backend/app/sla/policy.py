"""Targets, priority-change rules, badge computation. Implements: SLA-1, SLA-2, SLA-5, SLA-6,
SLA-7, SLA-8, WAIT-1, WAIT-3, WAIT-4, RO-1, RO-3, PRI-1, PRI-2, PRI-3, PRI-4; D-024, D-025,
D-026.

Pure module: no FastAPI, no SQLAlchemy, no clock (test A-2). The caller always passes `now`
(the request's DB time, ARCHITECTURE §6) and the holiday set.

Clock invariants (mirrors the ticket columns of the same names):
- running:  paused_at is None, resolved_at is None, resolution_remaining_min is None.
- paused:   paused_at set; resolution_remaining_min = max(remaining at pause, 0) (shown by the
            badge, adjusted by PRI-4). While paused resolution_due_at is the pre-pause value
            (moved only by a priority change); on resume it moves forward by the waiting time.
- resolved: resolved_at set; resolution_remaining_min = max(remaining at resolve, 0). On a
            reopen the due moves forward by the resolved time (D-013, D-026).
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from app.sla.calendar import Holidays, add_working_minutes, working_minutes_between


class Priority(StrEnum):
    """Ticket priority (SLA-1). Shared by the ORM models; defined here so app/sla stays pure."""

    urgent = "urgent"
    medium = "medium"
    low = "low"


# SLA-2 / D-009: (first response, resolution) in working minutes.
TARGETS: dict[Priority, tuple[int, int]] = {
    Priority.urgent: (120, 540),
    Priority.medium: (270, 1620),
    Priority.low: (540, 2700),
}
AT_RISK_FRACTION = 0.25  # SLA-8
AUTO_CLOSE_WORKING_MIN = 2700  # WAIT-4 / D-010: 5 working days × 540
REOPEN_WINDOW = timedelta(days=7)  # RO-1 / RO-3 / D-011: calendar days

# Lower rank = more urgent.
_RANK: dict[Priority, int] = {Priority.urgent: 0, Priority.medium: 1, Priority.low: 2}

BadgeState = Literal["late", "at_risk", "paused", "on_track", "met"]
TargetName = Literal["response", "resolution"]


@dataclass(frozen=True)
class Clock:
    """SLA-relevant snapshot of one ticket (ARCHITECTURE §3 ticket columns)."""

    priority: Priority
    created_at: datetime
    first_response_due_at: datetime
    first_response_at: datetime | None
    resolution_due_at: datetime
    resolved_at: datetime | None
    paused_at: datetime | None
    resolution_remaining_min: int | None


@dataclass(frozen=True)
class TargetStatus:
    """State of one target, for the ticket SLA panel which shows both (UI-4, D-025).

    minutes: late → working minutes overdue (frozen at met/pause time where applicable);
    at_risk / on_track / paused → working minutes left; met → working minutes to spare.
    """

    target: TargetName
    state: BadgeState
    minutes: int
    due_at: datetime
    met_at: datetime | None


@dataclass(frozen=True)
class Badge:
    """The single list-row badge (UI-2). Same meaning of `minutes` as TargetStatus."""

    state: BadgeState
    target: TargetName
    minutes: int


def targets(priority: Priority) -> tuple[int, int]:
    """SLA-2: (response, resolution) target in working minutes for `priority`."""
    return TARGETS[priority]


def initial_clock(priority: Priority, created_at: datetime, holidays: Holidays) -> Clock:
    """SLA-2, SLA-3, SLA-4: both due times counted in working minutes from creation."""
    response_min, resolution_min = TARGETS[priority]
    return Clock(
        priority=priority,
        created_at=created_at,
        first_response_due_at=add_working_minutes(created_at, response_min, holidays),
        first_response_at=None,
        resolution_due_at=add_working_minutes(created_at, resolution_min, holidays),
        resolved_at=None,
        paused_at=None,
        resolution_remaining_min=None,
    )


def pause(clock: Clock, now: datetime, holidays: Holidays) -> Clock:
    """WAIT-1, WAIT-3: stop the resolution clock and store the remaining working minutes.

    Stores max(remaining, 0). The due time is left untouched, so a ticket that is already
    overdue keeps its old due time (breach preserved).
    """
    if clock.paused_at is not None:
        raise ValueError("clock is already paused")
    if clock.resolved_at is not None:
        raise ValueError("cannot pause a resolved ticket")
    remaining = working_minutes_between(now, clock.resolution_due_at, holidays)
    return replace(clock, paused_at=now, resolution_remaining_min=max(remaining, 0))


def resume(clock: Clock, now: datetime, holidays: Holidays) -> Clock:
    """WAIT-3 (customer replies to a waiting ticket) and RO-1 / D-013 (reopen of a resolved one).

    D-026: due = old_due + working_minutes_between(paused_at or resolved_at, now). The time
    spent waiting on the customer (or resolved) is excluded for every ticket: an on-time
    ticket lands on now + remaining; a breached one stays late by exactly the amount it was
    late at the pause/resolve and keeps counting from there. Clears paused_at, resolved_at
    and the stored remaining, so the resolution target is unmet and running again.
    """
    stopped_at = clock.paused_at if clock.paused_at is not None else clock.resolved_at
    if stopped_at is None:
        raise ValueError("clock is neither paused nor resolved")
    waited = working_minutes_between(stopped_at, now, holidays)
    return replace(
        clock,
        resolution_due_at=add_working_minutes(clock.resolution_due_at, waited, holidays),
        paused_at=None,
        resolved_at=None,
        resolution_remaining_min=None,
    )


def resolve(clock: Clock, now: datetime, holidays: Holidays) -> Clock:
    """SLA-6: resolution is met now. Stores max(remaining, 0) like pause, for a reopen (D-013)."""
    if clock.resolved_at is not None:
        raise ValueError("clock is already resolved")
    if clock.paused_at is not None:
        raise ValueError("cannot resolve a paused clock; resume first")
    remaining = working_minutes_between(now, clock.resolution_due_at, holidays)
    return replace(clock, resolved_at=now, resolution_remaining_min=max(remaining, 0))


def _changed_remaining(old_target: int, new_target: int, remaining: int, upgrade: bool) -> int:
    """PRI-1 / PRI-4 (upgrade: min) and D-024 (downgrade: new − (old − remaining))."""
    if upgrade:
        return min(remaining, new_target)
    return new_target - (old_target - remaining)


def _changed_running_due(
    old_due: datetime,
    old_target: int,
    new_target: int,
    upgrade: bool,
    now: datetime,
    holidays: Holidays,
) -> datetime:
    """PRI-1 / PRI-2 for a running (not paused) target.

    Downgrade (D-024): due = now + remaining_new with remaining_new = new − (old −
    remaining_now). Since now + remaining_now is old_due, this is computed as
    old_due + (new − old) working minutes: the same value, but exact to the second (no
    minute truncation) and with no 18:30-vs-next-09:30 ambiguity when remaining_new ≤ 0.
    """
    if upgrade:
        return min(old_due, add_working_minutes(now, new_target, holidays))
    return add_working_minutes(old_due, new_target - old_target, holidays)


def change_priority(
    clock: Clock, new_priority: Priority, now: datetime, holidays: Holidays
) -> Clock:
    """PRI-1..PRI-4, D-024: recompute unmet due times after a priority change.

    - PRI-3: a met target (response replied / resolution resolved) is not recalculated.
    - PRI-1 upgrade: due = min(old due, now + new target).
    - PRI-2 / D-024 downgrade: remaining_new = new − (old − remaining_now); due = now +
      remaining_new (computed as old_due + (new − old), see _changed_running_due), so an
      overdue ticket still lands on "created_at + new target excluding paused time".
    - PRI-4 paused: the same rules adjust the stored remaining minutes (floored at 0), and
      the preserved due time moves by the same delta (new − old remaining), so resume
      (D-026: due + waiting time) lands on resume time + new remaining, and a still-overdue
      ticket's frozen overdue amount equals −result.
    """
    if new_priority == clock.priority:
        return clock
    upgrade = _RANK[new_priority] < _RANK[clock.priority]
    old_resp, old_res = TARGETS[clock.priority]
    new_resp, new_res = TARGETS[new_priority]

    response_due = clock.first_response_due_at
    if clock.first_response_at is None:
        response_due = _changed_running_due(
            response_due, old_resp, new_resp, upgrade, now, holidays
        )

    resolution_due = clock.resolution_due_at
    stored = clock.resolution_remaining_min
    if clock.resolved_at is not None:
        pass  # PRI-3: resolution already met
    elif clock.paused_at is not None:
        paused_at = clock.paused_at
        if stored is None:
            raise ValueError("paused clock has no stored remaining minutes")
        signed = stored if stored > 0 else working_minutes_between(
            paused_at, resolution_due, holidays
        )
        new_remaining = _changed_remaining(old_res, new_res, signed, upgrade)
        stored = max(new_remaining, 0)
        delta = new_remaining - signed
        if delta:
            resolution_due = add_working_minutes(resolution_due, delta, holidays)
    else:
        resolution_due = _changed_running_due(
            resolution_due, old_res, new_res, upgrade, now, holidays
        )

    return replace(
        clock,
        priority=new_priority,
        first_response_due_at=response_due,
        resolution_due_at=resolution_due,
        resolution_remaining_min=stored,
    )


def _met_status(target: TargetName, due: datetime, met_at: datetime, holidays: Holidays
                ) -> TargetStatus:
    """SLA-7: a met target is late if it was met after its due time."""
    if met_at > due:
        return TargetStatus(target, "late", working_minutes_between(due, met_at, holidays),
                            due, met_at)
    return TargetStatus(target, "met", working_minutes_between(met_at, due, holidays), due, met_at)


def _running_status(
    target: TargetName, due: datetime, target_min: int, now: datetime, holidays: Holidays
) -> TargetStatus:
    """SLA-7 (late: unmet and now > due) and SLA-8 (at risk: < 25% of the target left)."""
    if now > due:
        return TargetStatus(target, "late", working_minutes_between(due, now, holidays), due, None)
    left = working_minutes_between(now, due, holidays)
    state: BadgeState = "at_risk" if left < AT_RISK_FRACTION * target_min else "on_track"
    return TargetStatus(target, state, left, due, None)


def response_status(clock: Clock, now: datetime, holidays: Holidays) -> TargetStatus:
    """SLA-5, SLA-7, SLA-8 for the first-response target (never paused)."""
    due = clock.first_response_due_at
    if clock.first_response_at is not None:
        return _met_status("response", due, clock.first_response_at, holidays)
    return _running_status("response", due, TARGETS[clock.priority][0], now, holidays)


def resolution_status(clock: Clock, now: datetime, holidays: Holidays) -> TargetStatus:
    """SLA-6, SLA-7, SLA-8, WAIT-1, WAIT-3, D-025 for the resolution target.

    Paused with minutes left → paused. Paused with the breach preserved → late, and the
    overdue minutes are FROZEN at the pause instant (customer waiting time is not counted
    against the team, D-025).
    """
    due = clock.resolution_due_at
    if clock.resolved_at is not None:
        return _met_status("resolution", due, clock.resolved_at, holidays)
    if clock.paused_at is not None:
        stored = clock.resolution_remaining_min or 0
        if stored > 0:
            return TargetStatus("resolution", "paused", stored, due, None)
        if clock.paused_at > due:
            overdue = working_minutes_between(due, clock.paused_at, holidays)
            return TargetStatus("resolution", "late", overdue, due, None)
        return TargetStatus("resolution", "paused", 0, due, None)
    return _running_status("resolution", due, TARGETS[clock.priority][1], now, holidays)


def target_statuses(
    clock: Clock, now: datetime, holidays: Holidays
) -> tuple[TargetStatus, TargetStatus]:
    """UI-4 / D-025: both targets separately (response, resolution) for the SLA panel."""
    return response_status(clock, now, holidays), resolution_status(clock, now, holidays)


def badge(clock: Clock, now: datetime, holidays: Holidays) -> Badge:
    """UI-2, SLA-7, SLA-8, D-025: the one badge for a list row.

    Late is sticky: once any target is missed the badge is late for that target (if both
    were missed, resolution). Otherwise the response target is shown until it is met, then
    the resolution target (at_risk / on_track / paused / met).
    """
    response, resolution = target_statuses(clock, now, holidays)
    if resolution.state == "late":
        chosen = resolution
    elif response.state == "late" or response.met_at is None:
        chosen = response
    else:
        chosen = resolution
    return Badge(state=chosen.state, target=chosen.target, minutes=chosen.minutes)


def should_auto_close(paused_at: datetime, now: datetime, holidays: Holidays) -> bool:
    """WAIT-4 / D-010: close after 5 working days of customer silence.

    D-025 boundary convention: the window ends AT the boundary, so exactly 2700 working
    minutes after paused_at already closes (>=).
    """
    return working_minutes_between(paused_at, now, holidays) >= AUTO_CLOSE_WORKING_MIN


def can_reopen(resolved_at: datetime, now: datetime) -> bool:
    """RO-1 / RO-2 / D-011: the customer may reopen within 7 calendar days of resolved_at.

    D-025 boundary convention: true only while now − resolved_at < 7 days; the exact 7-day
    instant already belongs to "expired" (RO-3 sweep closes when this is false).
    """
    for name, value in (("resolved_at", resolved_at), ("now", now)):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
    return now - resolved_at < REOPEN_WINDOW
