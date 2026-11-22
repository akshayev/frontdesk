"""State machine and use cases (claim, reply, note, wait, resolve, reopen, priority). Implements:
CLM-1, CLM-2, CLM-3, SLA-5, SLA-6, WAIT-2, WAIT-3, RO-1, RO-2, RO-4, PRI-1..PRI-5, IN-1, IN-2,
AUD-1, LEAK-3; D-012, D-013, D-020, D-021, D-026, D-027.

Every mutation follows one recipe (ARCHITECTURE §7, CLAUDE.md):
  lock the ticket row (SELECT … FOR UPDATE; 404 if missing) → check expected_version (409
  stale_version) → check permission (403) and the §4 transition table (409) → apply →
  version += 1 → append audit event(s) with ctx.now — all inside the caller's transaction.
Claim is the one exception: it is a single atomic UPDATE … WHERE assignee_id IS NULL (§7).

ARCHITECTURE §4 is the only transition table; any other action is 409 illegal_transition.

Audit events: one event per action (types in ARCHITECTURE §8), plus `status_changed {from,
to}` whenever an action changes the status — except the new → open step of claim/assign, which
the `claimed` / `assigned` event itself records (the status is always `open` afterwards).
Payloads carry ids, never message or note text (LEAK-3).
"""

import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, select, update

from app.audit.chain import append_event
from app.db import RequestContext
from app.models import (
    SUBJECT_MAX,
    ActorType,
    Agent,
    AgentRole,
    AuthorType,
    CloseReason,
    Customer,
    InternalNote,
    Message,
    Ticket,
    TicketStatus,
)
from app.security.customer_token import generate_token
from app.sla import policy
from app.sla.calendar import Holidays
from app.sla.policy import Priority

S = TicketStatus
Channel = Literal["public", "agent", "followup"]

# The action names the UI may offer (allowed_actions).
ACTIONS = ("claim", "release", "assign", "reply", "reply_and_wait", "note", "resolve",
           "change_priority")


class DomainError(Exception):
    """A rule violation, mapped by the API to {error: code, message, request_id, **extra}."""

    def __init__(self, code: str, http_status: int, message: str,
                 extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.message = message
        self.extra = extra or {}


def not_found() -> DomainError:
    """404: the ticket does not exist (or is outside the caller's scope, I-14)."""
    return DomainError("not_found", 404, "Ticket not found.")


def forbidden(message: str) -> DomainError:
    """403: CLM-2 — the action belongs to the assignee (or the lead)."""
    return DomainError("forbidden", 403, message)


def illegal(message: str) -> DomainError:
    """409: the action is not in the ARCHITECTURE §4 transition table for this status."""
    return DomainError("illegal_transition", 409, message)


def validation(message: str) -> DomainError:
    """422: a request that is well-formed but refers to something invalid."""
    return DomainError("validation_error", 422, message)


@dataclass(frozen=True)
class Actor:
    """Who causes an audit event (AUD-1): agent, customer (id = customer id) or system."""

    type: ActorType
    id: uuid.UUID | None

    @staticmethod
    def of_agent(agent: Agent) -> "Actor":
        return Actor(ActorType.agent, agent.id)

    @staticmethod
    def of_customer(ticket: Ticket) -> "Actor":
        return Actor(ActorType.customer, ticket.customer_id)


SYSTEM = Actor(ActorType.system, None)


@dataclass(frozen=True)
class CustomerWriteResult:
    """Outcome of customer_message: the ticket written to, and — only for RO-4 — the raw
    token of the NEW ticket (returned once, never stored or logged)."""

    ticket: Ticket
    new_ticket_token: str | None = None


# --- helpers ---------------------------------------------------------------------------------


def lock_ticket(ctx: RequestContext, ticket_id: uuid.UUID) -> Ticket:
    """ARCHITECTURE §7: SELECT … FOR UPDATE the ticket row (fresh values), else 404."""
    ticket = ctx.session.scalars(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if ticket is None:
        raise not_found()
    return ticket


def check_version(ticket: Ticket, expected_version: int) -> None:
    """CLM-3 / D-020: the ticket changed since the caller loaded it → 409 stale_version."""
    if ticket.version != expected_version:
        raise DomainError(
            "stale_version", 409,
            "This ticket changed since you opened it. Review the latest activity before sending.",
            {"current_version": ticket.version},
        )


def clock_of(ticket: Ticket) -> policy.Clock:
    """The SLA snapshot of a ticket row (ARCHITECTURE §5)."""
    return policy.Clock(
        priority=ticket.priority,
        created_at=ticket.created_at,
        first_response_due_at=ticket.first_response_due_at,
        first_response_at=ticket.first_response_at,
        resolution_due_at=ticket.resolution_due_at,
        resolved_at=ticket.resolved_at,
        paused_at=ticket.paused_at,
        resolution_remaining_min=ticket.resolution_remaining_min,
    )


def apply_clock(ticket: Ticket, clock: policy.Clock) -> None:
    """Write an SLA snapshot back onto the ticket row."""
    ticket.priority = clock.priority
    ticket.first_response_due_at = clock.first_response_due_at
    ticket.first_response_at = clock.first_response_at
    ticket.resolution_due_at = clock.resolution_due_at
    ticket.resolved_at = clock.resolved_at
    ticket.paused_at = clock.paused_at
    ticket.resolution_remaining_min = clock.resolution_remaining_min


def _event(ctx: RequestContext, ticket: Ticket, actor: Actor, event_type: str,
           payload: dict[str, Any] | None = None) -> None:
    """AUD-1: one hash-chained event in the same transaction, at the request's DB now."""
    append_event(ctx.session, ctx.now, ticket.id, actor.type, actor.id, event_type,
                 payload or {})


def _set_status(ctx: RequestContext, ticket: Ticket, actor: Actor, to: TicketStatus) -> None:
    """Change the status and record status_changed {from, to} (AUD-1)."""
    old = ticket.status
    ticket.status = to
    _event(ctx, ticket, actor, "status_changed", {"from": old.value, "to": to.value})


def _bump(ctx: RequestContext, ticket: Ticket) -> None:
    """CLM-3: every successful mutation increments the version; flushed so the row is
    written before the next audit event / read in this transaction."""
    ticket.version += 1
    ctx.session.flush()


def _require_assignee(ticket: Ticket, agent: Agent, what: str) -> None:
    """CLM-2: only the assignee may reply, resolve or set waiting."""
    if ticket.assignee_id != agent.id:
        raise forbidden(f"Only the agent who owns this ticket can {what}.")


def _add_message(ctx: RequestContext, ticket: Ticket, author: AuthorType,
                 agent_id: uuid.UUID | None, body: str) -> Message:
    message = Message(ticket_id=ticket.id, author_type=author, author_agent_id=agent_id,
                      body=body, created_at=ctx.now)
    ctx.session.add(message)
    ctx.session.flush()
    return message


def _find_or_create_customer(ctx: RequestContext, name: str, email: str) -> Customer:
    """IN-1 / IN-2: reuse the customer with the same email (case-insensitive), else create."""
    email = email.strip().lower()
    customer = ctx.session.scalars(
        select(Customer).where(func.lower(Customer.email) == email).order_by(Customer.id).limit(1)
    ).first()
    if customer is None:
        customer = Customer(name=name.strip(), email=email)
        ctx.session.add(customer)
        ctx.session.flush()
    return customer


# --- create ----------------------------------------------------------------------------------


def _create(ctx: RequestContext, holidays: Holidays, *, customer: Customer, subject: str,
            body: str, priority: Priority, actor: Actor, channel: Channel,
            parent: Ticket | None = None) -> tuple[Ticket, str]:
    """Insert a `new` ticket with its initial SLA clock and first customer message."""
    clock = policy.initial_clock(priority, ctx.now, holidays)
    token, token_hash = generate_token()
    ticket = Ticket(
        subject=subject,
        customer_id=customer.id,
        status=S.new,
        version=0,
        created_at=ctx.now,
        customer_token_hash=token_hash,
        reopen_count=0,
        parent_ticket_id=None if parent is None else parent.id,
    )
    apply_clock(ticket, clock)
    ctx.session.add(ticket)
    ctx.session.flush()
    message = _add_message(ctx, ticket, AuthorType.customer, None, body)
    created: dict[str, Any] = {"number": ticket.number, "priority": priority.value,
                               "channel": channel, "customer_id": customer.id}
    if parent is not None:
        created["parent_ticket_id"] = parent.id
    _event(ctx, ticket, actor, "ticket_created", created)
    _event(ctx, ticket, actor, "customer_message", {"message_id": message.id})
    return ticket, token


def create_ticket(ctx: RequestContext, holidays: Holidays, *, channel: Literal["public", "agent"],
                  customer_name: str, customer_email: str, subject: str, body: str,
                  priority: Priority, agent: Agent | None = None) -> tuple[Ticket, str]:
    """IN-1 (public form, actor customer) / IN-2 (agent on behalf of a customer, actor agent).

    Status `new`, clock from policy.initial_clock (SLA-2..4), first message = the customer's
    description. Returns (ticket, raw token): the token is shown once as the secret link and
    only its sha256 is stored.
    """
    if channel == "agent" and agent is None:
        raise ValueError("agent channel requires the creating agent")
    customer = _find_or_create_customer(ctx, customer_name, customer_email)
    actor = Actor.of_agent(agent) if channel == "agent" and agent is not None else Actor(
        ActorType.customer, customer.id)
    return _create(ctx, holidays, customer=customer, subject=subject, body=body,
                   priority=priority, actor=actor, channel=channel)


# --- agent actions ---------------------------------------------------------------------------


def claim(ctx: RequestContext, ticket_id: uuid.UUID, agent: Agent) -> Ticket:
    """CLM-1 (INC-0291): atomic claim — exactly one concurrent caller can win.

    UPDATE … SET assignee_id = me, status = 'open', version = version + 1 WHERE id = :id AND
    assignee_id IS NULL AND status IN ('new', 'open') RETURNING id. PostgreSQL re-checks the
    WHERE clause after waiting for a competing writer's row lock, so the loser updates 0 rows.
    0 rows → 409 already_claimed with the owner's name, or 409 illegal_transition, or 404.
    """
    claimed_id = ctx.session.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.assignee_id.is_(None),
               Ticket.status.in_([S.new, S.open]))
        .values(assignee_id=agent.id, status=S.open, version=Ticket.version + 1)
        .returning(Ticket.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if claimed_id is None:
        ticket = ctx.session.get(Ticket, ticket_id, populate_existing=True)
        if ticket is None:
            raise not_found()
        if ticket.assignee_id is not None and ticket.status in (S.new, S.open,
                                                                 S.waiting_on_customer):
            owner = ctx.session.get(Agent, ticket.assignee_id)
            owner_name = owner.name if owner is not None else "another agent"
            raise DomainError(
                "already_claimed", 409, f"{owner_name} has already taken this ticket.",
                {"owner": {"id": str(ticket.assignee_id), "name": owner_name}},
            )
        raise illegal(f"A {ticket.status.value} ticket cannot be claimed.")
    ticket = ctx.session.get(Ticket, claimed_id, populate_existing=True)
    assert ticket is not None
    _event(ctx, ticket, Actor.of_agent(agent), "claimed")
    return ticket


def release(ctx: RequestContext, ticket_id: uuid.UUID, agent: Agent,
            expected_version: int) -> Ticket:
    """§4 open → release (assignee) → open, unassigned."""
    ticket = lock_ticket(ctx, ticket_id)
    check_version(ticket, expected_version)
    _require_assignee(ticket, agent, "release it")
    if ticket.status is not S.open:
        raise illegal("Only an open ticket can be released.")
    ticket.assignee_id = None
    _bump(ctx, ticket)
    _event(ctx, ticket, Actor.of_agent(agent), "released")
    return ticket


def assign(ctx: RequestContext, ticket_id: uuid.UUID, lead: Agent, to_agent_id: uuid.UUID,
           expected_version: int) -> Ticket:
    """§4 any non-closed → assign (lead) → same status, new assignee (new becomes open).
    CLM-2: the lead may reassign."""
    if lead.role is not AgentRole.lead:
        raise forbidden("Only the lead can assign tickets.")
    ticket = lock_ticket(ctx, ticket_id)
    check_version(ticket, expected_version)
    if ticket.status is S.closed:
        raise illegal("A closed ticket cannot be assigned.")
    target = ctx.session.get(Agent, to_agent_id)
    if target is None:
        raise validation("Unknown agent.")
    from_agent_id = ticket.assignee_id
    ticket.assignee_id = target.id
    if ticket.status is S.new:
        ticket.status = S.open
    _bump(ctx, ticket)
    _event(ctx, ticket, Actor.of_agent(lead), "assigned",
           {"from_agent_id": from_agent_id, "to_agent_id": target.id})
    return ticket


def agent_reply(ctx: RequestContext, holidays: Holidays, ticket_id: uuid.UUID, agent: Agent,
                body: str, expected_version: int, wait_for_customer: bool) -> Ticket:
    """Public reply by the assignee (CLM-2, UI-5).

    - SLA-5: the first public agent reply meets the response target (first_response_at).
    - WAIT-2: "and wait for customer" pauses the resolution clock (policy.pause) and sets
      waiting_on_customer — the only way into that status.
    - §4: only from open; a new ticket must be claimed first.
    """
    ticket = lock_ticket(ctx, ticket_id)
    check_version(ticket, expected_version)
    if ticket.status is S.new:
        raise illegal("Claim this ticket before replying.")
    _require_assignee(ticket, agent, "reply to the customer")
    if ticket.status is not S.open:
        raise illegal(f"Cannot reply to a {ticket.status.value} ticket.")
    message = _add_message(ctx, ticket, AuthorType.agent, agent.id, body)
    clock = clock_of(ticket)
    if clock.first_response_at is None:
        clock = replace(clock, first_response_at=ctx.now)
    if wait_for_customer:
        clock = policy.pause(clock, ctx.now, holidays)
    apply_clock(ticket, clock)
    actor = Actor.of_agent(agent)
    _event(ctx, ticket, actor, "agent_reply",
           {"message_id": message.id, "wait_for_customer": wait_for_customer})
    if wait_for_customer:
        _set_status(ctx, ticket, actor, S.waiting_on_customer)
    _bump(ctx, ticket)
    return ticket


def add_note(ctx: RequestContext, ticket_id: uuid.UUID, agent: Agent, body: str,
             expected_version: int) -> Ticket:
    """UI-5 internal note: any agent, any status; stored only in internal_notes (LEAK-2).

    Bumps the version on purpose (CLM-3): a colleague's guidance makes the assignee's next
    reply stale, so they must read it before sending. The event carries the note id only
    (LEAK-3).
    """
    ticket = lock_ticket(ctx, ticket_id)
    check_version(ticket, expected_version)
    note = InternalNote(ticket_id=ticket.id, agent_id=agent.id, body=body, created_at=ctx.now)
    ctx.session.add(note)
    ctx.session.flush()
    _bump(ctx, ticket)
    _event(ctx, ticket, Actor.of_agent(agent), "note_added", {"note_id": note.id})
    return ticket


def resolve(ctx: RequestContext, holidays: Holidays, ticket_id: uuid.UUID, agent: Agent,
            expected_version: int) -> Ticket:
    """§4 open → resolve (assignee) → resolved. SLA-6: resolution met now (policy.resolve).

    D-027: requires a met first response (at least one public agent reply), else 409
    reply_required.
    """
    ticket = lock_ticket(ctx, ticket_id)
    check_version(ticket, expected_version)
    _require_assignee(ticket, agent, "resolve it")
    if ticket.status is not S.open:
        raise illegal(f"A {ticket.status.value} ticket cannot be resolved.")
    if ticket.first_response_at is None:
        raise DomainError("reply_required", 409,
                          "Reply to the customer before resolving this ticket.")
    apply_clock(ticket, policy.resolve(clock_of(ticket), ctx.now, holidays))
    actor = Actor.of_agent(agent)
    _event(ctx, ticket, actor, "resolved")
    _set_status(ctx, ticket, actor, S.resolved)
    _bump(ctx, ticket)
    return ticket


def _iso(value: datetime) -> str:
    return value.isoformat()


def change_priority(ctx: RequestContext, holidays: Holidays, ticket_id: uuid.UUID,
                    agent: Agent, new_priority: Priority, expected_version: int) -> Ticket:
    """§4 new/open/waiting → change priority (assignee or lead). PRI-1..PRI-4 via
    policy.change_priority; PRI-5: priority_changed records old/new priority and due times."""
    ticket = lock_ticket(ctx, ticket_id)
    check_version(ticket, expected_version)
    if ticket.assignee_id != agent.id and agent.role is not AgentRole.lead:
        raise forbidden("Only the ticket's owner or the lead can change its priority.")
    if ticket.status not in (S.new, S.open, S.waiting_on_customer):
        raise illegal(f"Priority cannot change on a {ticket.status.value} ticket.")
    if new_priority == ticket.priority:
        raise validation(f"The ticket is already {new_priority.value}.")
    old = clock_of(ticket)
    new = policy.change_priority(old, new_priority, ctx.now, holidays)
    apply_clock(ticket, new)
    _bump(ctx, ticket)
    _event(ctx, ticket, Actor.of_agent(agent), "priority_changed", {
        "from": old.priority.value,
        "to": new.priority.value,
        "old_response_due": _iso(old.first_response_due_at),
        "new_response_due": _iso(new.first_response_due_at),
        "old_resolution_due": _iso(old.resolution_due_at),
        "new_resolution_due": _iso(new.resolution_due_at),
    })
    return ticket


# --- customer actions ------------------------------------------------------------------------


def _reopen(ctx: RequestContext, holidays: Holidays, ticket: Ticket, actor: Actor) -> None:
    """RO-1 / D-013 / D-026: resume the resolution clock (due moves by the resolved time)."""
    apply_clock(ticket, policy.resume(clock_of(ticket), ctx.now, holidays))
    ticket.reopen_count += 1
    _event(ctx, ticket, actor, "reopened", {"reopen_count": ticket.reopen_count})
    _set_status(ctx, ticket, actor, S.open)


def _reopenable(ticket: Ticket, now: datetime) -> bool:
    return (ticket.status is S.resolved and ticket.resolved_at is not None
            and policy.can_reopen(ticket.resolved_at, now))


def _followup_subject(subject: str) -> str:
    return f"Re: {subject}"[:SUBJECT_MAX]


def customer_message(ctx: RequestContext, holidays: Holidays, ticket_id: uuid.UUID,
                     body: str) -> CustomerWriteResult:
    """A customer writes on their ticket. No expected_version (the customer page has none),
    but the version is bumped so an agent's stale write gets 409 (CLM-3).

    - new / open → message only.
    - waiting_on_customer → WAIT-3 / D-026: resume the clock, status open.
    - resolved inside the window → RO-2: reopen (as RO-1), reopen_count + 1.
    - resolved past the window, or closed → RO-4 / D-012: a NEW ticket for the same customer,
      subject "Re: <old subject>", same priority, parent_ticket_id = old; the old ticket is
      not changed. The new raw token is returned once.
    """
    ticket = lock_ticket(ctx, ticket_id)
    actor = Actor.of_customer(ticket)
    if ticket.status is S.closed or (ticket.status is S.resolved
                                     and not _reopenable(ticket, ctx.now)):
        customer = ctx.session.get(Customer, ticket.customer_id)
        assert customer is not None
        child, token = _create(ctx, holidays, customer=customer,
                               subject=_followup_subject(ticket.subject), body=body,
                               priority=ticket.priority, actor=actor, channel="followup",
                               parent=ticket)
        return CustomerWriteResult(ticket=child, new_ticket_token=token)

    message = _add_message(ctx, ticket, AuthorType.customer, None, body)
    _event(ctx, ticket, actor, "customer_message", {"message_id": message.id})
    if ticket.status is S.waiting_on_customer:
        apply_clock(ticket, policy.resume(clock_of(ticket), ctx.now, holidays))
        _set_status(ctx, ticket, actor, S.open)
    elif ticket.status is S.resolved:
        _reopen(ctx, holidays, ticket, actor)
    _bump(ctx, ticket)
    return CustomerWriteResult(ticket=ticket)


def customer_reopen(ctx: RequestContext, holidays: Holidays, ticket_id: uuid.UUID) -> Ticket:
    """RO-1: the customer reopens a resolved ticket within 7 calendar days (D-011, D-025).
    Past the window → 409 reopen_window_expired; any other status → 409 illegal_transition."""
    ticket = lock_ticket(ctx, ticket_id)
    if ticket.status is not S.resolved:
        raise illegal(f"A {ticket.status.value} ticket cannot be reopened.")
    if not _reopenable(ticket, ctx.now):
        raise DomainError("reopen_window_expired", 409,
                          "This ticket was resolved more than 7 days ago. "
                          "Send a message to open a new ticket.")
    _reopen(ctx, holidays, ticket, Actor.of_customer(ticket))
    _bump(ctx, ticket)
    return ticket


# --- system ----------------------------------------------------------------------------------


def auto_close(ctx: RequestContext, ticket: Ticket, reason: CloseReason) -> None:
    """WAIT-4 / RO-3: the sweep closes a (locked) ticket as actor system. The SLA columns are
    left as they were, so a closed ticket keeps its final (frozen) SLA state."""
    ticket.closed_at = ctx.now
    ticket.close_reason = reason
    _event(ctx, ticket, SYSTEM, "auto_closed", {"reason": reason.value})
    _set_status(ctx, ticket, SYSTEM, S.closed)
    _bump(ctx, ticket)


# --- read side -------------------------------------------------------------------------------


def allowed_actions(ticket: Ticket, agent: Agent) -> list[str]:
    """The actions the server would accept from `agent` right now (ignoring version), in
    ACTIONS order. Mirrors the checks above so the UI never offers a button that 403/409s."""
    status = ticket.status
    mine = ticket.assignee_id == agent.id
    lead = agent.role is AgentRole.lead
    allowed: set[str] = {"note"}
    if ticket.assignee_id is None and status in (S.new, S.open):
        allowed.add("claim")
    if mine and status is S.open:
        allowed.update({"release", "reply", "reply_and_wait"})
        if ticket.first_response_at is not None:
            allowed.add("resolve")
    if lead and status is not S.closed:
        allowed.add("assign")
    if (mine or lead) and status in (S.new, S.open, S.waiting_on_customer):
        allowed.add("change_priority")
    return [a for a in ACTIONS if a in allowed]
