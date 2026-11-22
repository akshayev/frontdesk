"""Targets, priority-change rules, badge computation. Implements: SLA-1, SLA-2, SLA-5, SLA-6,
SLA-7, SLA-8, WAIT-1, WAIT-3, PRI-1, PRI-2, PRI-3, PRI-4.
"""

from enum import StrEnum


class Priority(StrEnum):
    """Ticket priority (SLA-1). Shared by the ORM models; defined here so app/sla stays pure."""

    urgent = "urgent"
    medium = "medium"
    low = "low"
