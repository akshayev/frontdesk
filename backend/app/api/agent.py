"""Agent API. Implements: UI-1, UI-2, UI-3, UI-4, UI-5, UI-6, UI-7, CLM-1, CLM-2, CLM-3, IN-2,
AUD-4, LEAK-1, D-034.

Every endpoint: require_agent (session cookie), CSRF header on writes (middleware), rate-limit
group `agent` (120/min/session). Every mutation goes through app/domain/tickets.py and returns
the fresh ticket page, so the client always holds the new `version`.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on

from app.api.csv_export import csv_response, ist
from app.db import RequestContext, Tx, load_holidays
from app.domain import tickets as domain
from app.models import (
    ActorType,
    Agent,
    AuditEvent,
    AuthorType,
    Customer,
    InternalNote,
    Message,
    Ticket,
    TicketStatus,
)
from app.schemas.agent import (
    AgentRef,
    BadgeOut,
    CustomerRef,
    EventOut,
    MessageOut,
    NoteIn,
    NoteOut,
    PriorityIn,
    ReplyIn,
    TargetStatusOut,
    TicketCreatedOut,
    TicketCreateIn,
    TicketDetail,
    TicketOut,
    TicketRow,
    VersionIn,
    View,
)
from app.security.customer_token import customer_link
from app.security.ratelimit import limit_agent
from app.security.sessions import CurrentAgent
from app.sla import policy
from app.sla.calendar import Holidays

router = APIRouter(prefix="/api/agent", tags=["agent"])

S = TicketStatus
ACTIVE = (S.new, S.open, S.waiting_on_customer)
LIST_CAP = 200
PREVIEW_CHARS = 140


def _agent_names(ctx: RequestContext, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return dict(ctx.session.execute(
        select(Agent.id, Agent.name).where(Agent.id.in_(wanted))).all())


def _ref(names: dict[uuid.UUID, str], agent_id: uuid.UUID | None) -> AgentRef | None:
    if agent_id is None:
        return None
    return AgentRef(id=agent_id, name=names.get(agent_id, "Unknown agent"))


def _badge(ticket: Ticket, now: datetime, holidays: Holidays) -> tuple[BadgeOut, datetime]:
    """UI-2 badge and the due time of the target it shows."""
    badge = policy.badge(domain.clock_of(ticket), now, holidays)
    due = ticket.first_response_due_at if badge.target == "response" else ticket.resolution_due_at
    return BadgeOut(state=badge.state, target=badge.target, minutes=badge.minutes), due


# --- list ------------------------------------------------------------------------------------


def _list_query(view: View, agent: Agent, active: bool):  # type: ignore[no-untyped-def]
    """D-034 view filters. Mine: mine & new/open/waiting/resolved; Unassigned: unassigned &
    new/open; Late: active (badge filtered later); Waiting; All: every status. `active`
    selects the new/open/waiting part or the resolved/closed part of the view."""
    last = (select(AuditEvent.ticket_id, func.max(AuditEvent.created_at).label("at"))
            .where(AuditEvent.ticket_id.is_not(None))
            .group_by(AuditEvent.ticket_id).subquery())
    last_at = func.coalesce(last.c.at, Ticket.created_at).label("last_activity_at")
    query = (select(Ticket, Customer.name, last_at)
             .join(Customer, Customer.id == Ticket.customer_id)
             .outerjoin(last, last.c.ticket_id == Ticket.id))
    statuses = {
        "mine": (*ACTIVE, S.resolved),
        "unassigned": (S.new, S.open),
        "late": ACTIVE,
        "waiting": (S.waiting_on_customer,),
        "all": tuple(S),
    }[view]
    part = [s for s in statuses if (s in ACTIVE) == active]
    query = query.where(Ticket.status.in_(part))
    if view == "mine":
        query = query.where(Ticket.assignee_id == agent.id)
    elif view == "unassigned":
        query = query.where(Ticket.assignee_id.is_(None))
    if not active:
        query = query.order_by(last_at.desc()).limit(LIST_CAP)
    return query, bool(part)


def _previews(ctx: RequestContext, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """UI-3 / LEAK-1: the latest PUBLIC message per ticket (messages table only)."""
    if not ids:
        return {}
    rows = ctx.session.execute(
        select(Message.ticket_id, Message.body)
        .where(Message.ticket_id.in_(ids))
        .ext(distinct_on(Message.ticket_id))
        .order_by(Message.ticket_id, Message.created_at.desc(), Message.id.desc())
    ).all()
    return {tid: body[:PREVIEW_CHARS] for tid, body in rows}


@router.get("/tickets", response_model=list[TicketRow])
@limit_agent
def list_tickets(request: Request, ctx: Tx, agent: CurrentAgent,
                 view: Annotated[View, Query()] = "mine") -> list[TicketRow]:
    """UI-1 / UI-2 / D-034. Active tickets first — late first (most overdue), then nearest
    due — then resolved/closed by most recent activity; at most 200 rows. Late view = badge
    late."""
    holidays = load_holidays(ctx.session)
    built: list[tuple[tuple[int, float], Ticket, str, datetime, BadgeOut, datetime]] = []
    for active in (True, False):
        query, any_status = _list_query(view, agent, active)
        if not any_status:
            continue
        for ticket, customer_name, last_at in ctx.session.execute(query):
            badge, due = _badge(ticket, ctx.now, holidays)
            if view == "late" and badge.state != "late":
                continue
            if not active:
                key = (2, -last_at.timestamp())
            elif badge.state == "late":
                key = (0, -float(badge.minutes))
            else:
                key = (1, due.timestamp())
            built.append((key, ticket, customer_name, last_at, badge, due))
    built.sort(key=lambda item: item[0])
    built = built[:LIST_CAP]
    previews = _previews(ctx, [t.id for _, t, *_ in built])
    names = _agent_names(ctx, {t.assignee_id for _, t, *_ in built})
    return [
        TicketRow(id=t.id, number=t.number, subject=t.subject, customer_name=customer_name,
                  priority=t.priority, status=t.status, assignee=_ref(names, t.assignee_id),
                  badge=badge, due_at=due, preview=previews.get(t.id, ""),
                  last_activity_at=last_at, version=t.version)
        for _, t, customer_name, last_at, badge, due in built
    ]


# --- detail ----------------------------------------------------------------------------------


def _load(ctx: RequestContext, ticket_id: uuid.UUID) -> Ticket:
    ticket = ctx.session.get(Ticket, ticket_id, populate_existing=True)
    if ticket is None:
        raise domain.not_found()
    return ticket


def ticket_detail(ctx: RequestContext, ticket: Ticket, agent: Agent) -> TicketDetail:
    """UI-4: conversation, notes (agent-only), timeline with actor names, SLA panel."""
    holidays = load_holidays(ctx.session)
    customer = ctx.session.get(Customer, ticket.customer_id)
    assert customer is not None
    messages = list(ctx.session.scalars(
        select(Message).where(Message.ticket_id == ticket.id)
        .order_by(Message.created_at, Message.id)))
    notes = list(ctx.session.scalars(
        select(InternalNote).where(InternalNote.ticket_id == ticket.id)
        .order_by(InternalNote.created_at, InternalNote.id)))
    events = list(ctx.session.scalars(
        select(AuditEvent).where(AuditEvent.ticket_id == ticket.id).order_by(AuditEvent.id)))
    names = _agent_names(ctx, {ticket.assignee_id}
                         | {m.author_agent_id for m in messages}
                         | {n.agent_id for n in notes}
                         | {e.actor_id for e in events if e.actor_type is ActorType.agent})

    def actor_name(event: AuditEvent) -> str:
        if event.actor_type is ActorType.system:
            return "System"
        if event.actor_type is ActorType.customer:
            return customer.name
        return names.get(event.actor_id, "Unknown agent") if event.actor_id else "Unknown agent"

    clock = domain.clock_of(ticket)
    badge, _ = _badge(ticket, ctx.now, holidays)
    return TicketDetail(
        ticket=TicketOut(
            id=ticket.id, number=ticket.number, subject=ticket.subject,
            customer=CustomerRef(id=customer.id, name=customer.name, email=customer.email),
            priority=ticket.priority, status=ticket.status,
            assignee=_ref(names, ticket.assignee_id), created_at=ticket.created_at,
            first_response_at=ticket.first_response_at, resolved_at=ticket.resolved_at,
            closed_at=ticket.closed_at, close_reason=ticket.close_reason,
            parent_ticket_id=ticket.parent_ticket_id, reopen_count=ticket.reopen_count,
            version=ticket.version),
        targets=[TargetStatusOut(target=s.target, state=s.state, minutes=s.minutes,
                                 due_at=s.due_at, met_at=s.met_at)
                 for s in policy.target_statuses(clock, ctx.now, holidays)],
        badge=badge,
        messages=[MessageOut(id=m.id, author_type=m.author_type.value,
                             author=_ref(names, m.author_agent_id), body=m.body,
                             created_at=m.created_at) for m in messages],
        notes=[NoteOut(id=n.id, author=AgentRef(id=n.agent_id,
                                                name=names.get(n.agent_id, "Unknown agent")),
                       body=n.body, created_at=n.created_at) for n in notes],
        events=[EventOut(id=e.id, event_type=e.event_type, actor_type=e.actor_type.value,
                         actor_id=e.actor_id, actor_name=actor_name(e), payload=e.payload,
                         created_at=e.created_at) for e in events],
        allowed_actions=domain.allowed_actions(ticket, agent),
        version=ticket.version,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
@limit_agent
def get_ticket(request: Request, ticket_id: uuid.UUID, ctx: Tx,
               agent: CurrentAgent) -> TicketDetail:
    """UI-4 ticket page."""
    return ticket_detail(ctx, _load(ctx, ticket_id), agent)


@router.get("/tickets/{ticket_id}/transcript.csv")
@limit_agent
def transcript(request: Request, ticket_id: uuid.UUID, ctx: Tx, agent: CurrentAgent) -> Response:
    """LEAK-1: PUBLIC messages only (messages table), formula-guarded CSV, IST seconds."""
    ticket = _load(ctx, ticket_id)
    customer = ctx.session.get(Customer, ticket.customer_id)
    assert customer is not None
    messages = list(ctx.session.scalars(
        select(Message).where(Message.ticket_id == ticket.id)
        .order_by(Message.created_at, Message.id)))
    names = _agent_names(ctx, {m.author_agent_id for m in messages})

    def author(m: Message) -> str:
        if m.author_type is AuthorType.customer:
            return f"Customer: {customer.name}"
        return f"Support: {names.get(m.author_agent_id, 'Unknown agent')}" \
            if m.author_agent_id else "Support"

    return csv_response(f"FD-{ticket.number}-transcript.csv", ["time_ist", "author", "message"],
                        ([ist(m.created_at), author(m), m.body] for m in messages))


# --- mutations -------------------------------------------------------------------------------


@router.post("/tickets", response_model=TicketCreatedOut, status_code=201)
@limit_agent
def create_ticket(request: Request, body: TicketCreateIn, ctx: Tx,
                  agent: CurrentAgent) -> TicketCreatedOut:
    """IN-2: create on behalf of a customer; the customer link is in this response only."""
    ticket, token = domain.create_ticket(
        ctx, load_holidays(ctx.session), channel="agent", customer_name=body.customer_name,
        customer_email=str(body.customer_email), subject=body.subject, body=body.body,
        priority=body.priority, agent=agent)
    return TicketCreatedOut(id=ticket.id, number=ticket.number,
                            customer_link=customer_link(
                                request.app.state.settings.public_base_url, token))


@router.post("/tickets/{ticket_id}/claim", response_model=TicketDetail)
@limit_agent
def claim(request: Request, ticket_id: uuid.UUID, ctx: Tx, agent: CurrentAgent) -> TicketDetail:
    """CLM-1 "Take this ticket": atomic; the loser gets 409 already_claimed + owner name."""
    return ticket_detail(ctx, domain.claim(ctx, ticket_id, agent), agent)


@router.post("/tickets/{ticket_id}/release", response_model=TicketDetail)
@limit_agent
def release(request: Request, ticket_id: uuid.UUID, body: VersionIn, ctx: Tx,
            agent: CurrentAgent) -> TicketDetail:
    """§4 release by the assignee."""
    ticket = domain.release(ctx, ticket_id, agent, body.expected_version)
    return ticket_detail(ctx, ticket, agent)


@router.post("/tickets/{ticket_id}/replies", response_model=TicketDetail)
@limit_agent
def reply(request: Request, ticket_id: uuid.UUID, body: ReplyIn, ctx: Tx,
          agent: CurrentAgent) -> TicketDetail:
    """UI-5 reply to customer (+ wait, WAIT-2). Assignee only (CLM-2)."""
    ticket = domain.agent_reply(ctx, load_holidays(ctx.session), ticket_id, agent, body.body,
                                body.expected_version, body.wait_for_customer)
    return ticket_detail(ctx, ticket, agent)


@router.post("/tickets/{ticket_id}/notes", response_model=TicketDetail)
@limit_agent
def note(request: Request, ticket_id: uuid.UUID, body: NoteIn, ctx: Tx,
         agent: CurrentAgent) -> TicketDetail:
    """UI-5 internal note (LEAK-2: stored in internal_notes only)."""
    ticket = domain.add_note(ctx, ticket_id, agent, body.body, body.expected_version)
    return ticket_detail(ctx, ticket, agent)


@router.post("/tickets/{ticket_id}/resolve", response_model=TicketDetail)
@limit_agent
def resolve(request: Request, ticket_id: uuid.UUID, body: VersionIn, ctx: Tx,
            agent: CurrentAgent) -> TicketDetail:
    """SLA-6 / D-027 resolve."""
    ticket = domain.resolve(ctx, load_holidays(ctx.session), ticket_id, agent,
                            body.expected_version)
    return ticket_detail(ctx, ticket, agent)


@router.patch("/tickets/{ticket_id}/priority", response_model=TicketDetail)
@limit_agent
def change_priority(request: Request, ticket_id: uuid.UUID, body: PriorityIn, ctx: Tx,
                    agent: CurrentAgent) -> TicketDetail:
    """PRI-1..PRI-5 priority change (assignee or lead)."""
    ticket = domain.change_priority(ctx, load_holidays(ctx.session), ticket_id, agent,
                                    body.priority, body.expected_version)
    return ticket_detail(ctx, ticket, agent)
