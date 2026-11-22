"""Demo data: `uv run python -m scripts.seed` (from backend/). Implements the S3 seed brief.

- Refuses to run unless the tickets table is empty; needs SEED_DEMO_PASSWORD (never
  hard-coded) for the 11 demo accounts (leads Meera and Rohini + 9 agents, @arvo.example).
  Two leads (D-044): the demo emails are public and lockout (D-029) can lock one of them.
- Builds ~20 tickets that cover every state (new, open, waiting, late response, late
  resolution, at risk, resolved, closed by both sweep reasons, priority change, reopen, a child
  of a closed ticket, notes). It does so by building a chronological list of actions with
  backdated `now` values, relative to the database's now(), and running them in time order
  through the DOMAIN functions and the sweep — never raw inserts for tickets, messages, notes
  or events — so the audit hash chain is valid and every timestamp is realistic.
- Offsets are in WORKING minutes before now, so badges (at risk, late) come out as described
  whatever day the seed runs.
- Prints verify() and counts per status; customer links only when APP_ENV=development.
"""

import sys
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.audit.chain import verify
from app.config import Settings, get_settings
from app.db import RequestContext, build_engine, load_holidays
from app.domain import tickets as d
from app.jobs.sweep import run_sweep
from app.models import Agent, AgentRole, Ticket
from app.security.customer_token import customer_link
from app.security.passwords import hash_password
from app.sla.calendar import Holidays, add_working_minutes
from app.sla.policy import AUTO_CLOSE_WORKING_MIN, REOPEN_WINDOW, Priority

# D-044: two leads, so one locked-out lead account cannot block an evaluation.
LEADS = [("Meera", "meera@arvo.example"), ("Rohini Krishnan", "rohini@arvo.example")]
AGENTS = [
    ("Priya Sharma", "priya@arvo.example"),
    ("Arjun Nair", "arjun@arvo.example"),
    ("Kavya Reddy", "kavya@arvo.example"),
    ("Rahul Verma", "rahul@arvo.example"),
    ("Ananya Iyer", "ananya@arvo.example"),
    ("Vikram Singh", "vikram@arvo.example"),
    ("Sneha Patil", "sneha@arvo.example"),
    ("Karthik Menon", "karthik@arvo.example"),
    ("Divya Joshi", "divya@arvo.example"),
]
CUSTOMERS = {
    "rohan": ("Rohan Mehta", "rohan.mehta@example.com"),
    "lakshmi": ("Lakshmi Narayanan", "lakshmi.n@example.com"),
    "farhan": ("Farhan Qureshi", "farhan.q@example.com"),
    "deepa": ("Deepa Kulkarni", "deepa.kulkarni@example.com"),
    "suresh": ("Suresh Babu", "suresh.babu@example.com"),
    "neha": ("Neha Agarwal", "neha.agarwal@example.com"),
    "manpreet": ("Manpreet Kaur", "manpreet.kaur@example.com"),
    "arvind": ("Arvind Rao", "arvind.rao@example.com"),
    "pooja": ("Pooja Desai", "pooja.desai@example.com"),
    "imran": ("Imran Sheikh", "imran.sheikh@example.com"),
    "gayathri": ("Gayathri Subramanian", "gayathri.s@example.com"),
    "tenzin": ("Tenzin Dorje", "tenzin.dorje@example.com"),
}
SWEEP_LAG = timedelta(minutes=5)  # the real sweep runs every 5 min


class SeedRefused(RuntimeError):
    """The seed would overwrite or mix with existing data, or is missing its password."""


@dataclass
class SeedReport:
    """What the seed created (for the CLI output and the seed test)."""

    verify_ok: bool
    verify_checked: int
    status_counts: dict[str, int]
    links: dict[str, str] = field(default_factory=dict)


Step = Callable[[RequestContext, Holidays], None]


@dataclass
class Timeline:
    """Chronological action list. Each action runs in its own transaction at its own `now`."""

    anchor: datetime
    holidays: Holidays
    actions: list[tuple[datetime, int, Step]] = field(default_factory=list)

    def w(self, working_minutes_ago: int) -> datetime:
        """The instant `working_minutes_ago` working minutes before the anchor."""
        return add_working_minutes(self.anchor, -working_minutes_ago, self.holidays)

    def at(self, when: datetime, step: Step) -> None:
        if when > self.anchor:
            raise ValueError(f"seed action in the future: {when.isoformat()}")
        self.actions.append((when, len(self.actions), step))


class Demo:
    """The seed's state: agent rows, ticket ids and the raw tokens (shown in dev only)."""

    def __init__(self, agents: dict[str, Agent]) -> None:
        self.agents = agents
        self.ids: dict[str, uuid.UUID] = {}
        self.tokens: dict[str, str] = {}

    def a(self, first_name: str) -> Agent:
        return self.agents[first_name]

    def version(self, ctx: RequestContext, key: str) -> int:
        ticket = ctx.session.get(Ticket, self.ids[key])
        assert ticket is not None
        return ticket.version

    # -- steps (each returns a Step closure for the timeline) --------------------------------

    def create(self, key: str, customer: str, subject: str, body: str, priority: Priority,
               by: str | None = None) -> Step:
        def step(ctx: RequestContext, holidays: Holidays) -> None:
            name, email = CUSTOMERS[customer]
            ticket, token = d.create_ticket(
                ctx, holidays, channel="agent" if by else "public", customer_name=name,
                customer_email=email, subject=subject, body=body, priority=priority,
                agent=self.a(by) if by else None)
            self.ids[key], self.tokens[key] = ticket.id, token
        return step

    def claim(self, key: str, agent: str) -> Step:
        def step(ctx: RequestContext, _h: Holidays) -> None:
            d.claim(ctx, self.ids[key], self.a(agent))
        return step

    def reply(self, key: str, agent: str, body: str, wait: bool = False) -> Step:
        def step(ctx: RequestContext, holidays: Holidays) -> None:
            d.agent_reply(ctx, holidays, self.ids[key], self.a(agent), body,
                          self.version(ctx, key), wait)
        return step

    def note(self, key: str, agent: str, body: str) -> Step:
        def step(ctx: RequestContext, _h: Holidays) -> None:
            d.add_note(ctx, self.ids[key], self.a(agent), body, self.version(ctx, key))
        return step

    def resolve(self, key: str, agent: str) -> Step:
        def step(ctx: RequestContext, holidays: Holidays) -> None:
            d.resolve(ctx, holidays, self.ids[key], self.a(agent), self.version(ctx, key))
        return step

    def priority(self, key: str, agent: str, new: Priority) -> Step:
        def step(ctx: RequestContext, holidays: Holidays) -> None:
            d.change_priority(ctx, holidays, self.ids[key], self.a(agent), new,
                              self.version(ctx, key))
        return step

    def release(self, key: str, agent: str) -> Step:
        def step(ctx: RequestContext, _h: Holidays) -> None:
            d.release(ctx, self.ids[key], self.a(agent), self.version(ctx, key))
        return step

    def assign(self, key: str, lead: str, to: str) -> Step:
        def step(ctx: RequestContext, _h: Holidays) -> None:
            d.assign(ctx, self.ids[key], self.a(lead), self.a(to).id, self.version(ctx, key))
        return step

    def customer_says(self, key: str, body: str, child_key: str | None = None) -> Step:
        def step(ctx: RequestContext, holidays: Holidays) -> None:
            result = d.customer_message(ctx, holidays, self.ids[key], body)
            if result.new_ticket_token is not None:
                assert child_key is not None, "unexpected RO-4 follow-up ticket"
                self.ids[child_key] = result.ticket.id
                self.tokens[child_key] = result.new_ticket_token
        return step

    @staticmethod
    def sweep() -> Step:
        def step(ctx: RequestContext, holidays: Holidays) -> None:
            run_sweep(ctx.session, ctx.now, holidays)
        return step


def _script(t: Timeline, demo: Demo) -> None:
    """The demo story. Every ticket's own actions are strictly increasing in time."""
    W, at, s = t.w, t.at, demo
    U, M, L = Priority.urgent, Priority.medium, Priority.low

    # T01 new, unassigned, on track
    at(W(30), s.create("T01", "rohan", "Invoice PDF shows the wrong GSTIN",
                       "The GSTIN on invoice INV-2291 is our old one. We updated it last week.",
                       M))
    # T02 new, unassigned, AT RISK (20 of 120 working minutes left)
    at(W(100), s.create("T02", "lakshmi", "Nobody in our team can log in",
                        "Since this morning every user gets 'session expired' right after "
                        "login. Our whole billing team is blocked.", U))
    # T03 claimed and answered, open, on track
    at(W(200), s.create("T03", "farhan", "How do I add a second warehouse?",
                        "We opened a new godown in Pune. Where do I add it?", L))
    at(W(190), s.claim("T03", "Priya"))
    at(W(180), s.reply("T03", "Priya", "Go to Settings → Locations → Add. I have attached "
                       "the steps in our help page. Does this answer it?"))
    # T04 waiting on customer (with a note)
    at(W(400), s.create("T04", "deepa", "Stock report totals do not match",
                        "The closing stock in the monthly report is 312 units more than the "
                        "item-wise list.", M))
    at(W(390), s.claim("T04", "Arjun"))
    at(W(385), s.note("T04", "Arjun", "Probably the negative-stock items. Need her export."))
    at(W(300), s.reply("T04", "Arjun", "Could you send us the Excel export of the item-wise "
                       "list for October?", wait=True))
    # T05 LATE RESPONSE: urgent, claimed, never answered
    at(W(300), s.create("T05", "suresh", "Payment gateway rejects all cards",
                        "Every card payment fails with error PG-502 since 10 am.", U))
    at(W(280), s.claim("T05", "Rahul"))
    at(W(100), s.note("T05", "Meera", "Rahul, this is urgent and overdue. Gateway status page "
                      "shows an incident; reply with an ETA please."))
    # T06 LATE RESOLUTION: urgent, answered in time, not resolved after 540 working minutes
    at(W(800), s.create("T06", "neha", "E-way bills not generating",
                        "Generating an e-way bill returns 'NIC timeout' for every invoice.", U))
    at(W(790), s.claim("T06", "Kavya"))
    at(W(760), s.reply("T06", "Kavya", "We see the NIC API timing out and are working on a "
                       "retry fix. I will update you within the hour."))
    at(W(700), s.note("T06", "Kavya", "Raised with engineering, ticket ENG-118."))
    at(W(400), s.note("T06", "Vikram", "ENG-118 fix is in review, deploy after QA."))
    # T07 resolved, inside the 7-day reopen window
    at(W(1200), s.create("T07", "manpreet", "Change the invoice logo",
                         "We have a new logo. How do I change it on printed invoices?", M))
    at(W(1190), s.claim("T07", "Ananya"))
    at(W(1100), s.reply("T07", "Ananya", "Settings → Print templates → Logo. Upload a PNG up "
                        "to 1 MB."))
    at(W(900), s.resolve("T07", "Ananya"))
    # T08 closed by the sweep: waiting, no customer reply for 5 working days
    at(W(4000), s.create("T08", "arvind", "Export to Tally fails",
                         "The Tally XML export stops at 60%.", L))
    at(W(3990), s.claim("T08", "Sneha"))
    paused = W(3500)
    at(paused, s.reply("T08", "Sneha", "Which Tally version are you on, and how many vouchers "
                       "are in the period?", wait=True))
    at(add_working_minutes(paused, AUTO_CLOSE_WORKING_MIN, t.holidays) + SWEEP_LAG, s.sweep())
    # T09 closed by the sweep: resolved more than 7 days ago; later the customer writes again
    at(W(5400), s.create("T09", "pooja", "Add a user for our accountant",
                         "Please add our CA as a read-only user.", M))
    at(W(5390), s.claim("T09", "Karthik"))
    at(W(5300), s.reply("T09", "Karthik", "Done — she will get an invite email. Read-only role "
                        "assigned."))
    resolved = W(5000)
    at(resolved, s.resolve("T09", "Karthik"))
    closed = resolved + REOPEN_WINDOW + SWEEP_LAG
    at(closed, s.sweep())
    # T12 child of the closed T09 (RO-4): the customer writes on the closed ticket
    at(closed + timedelta(days=1), s.customer_says(
        "T09", "Our CA says the invite link has expired. Can you resend it?", child_key="T12"))
    # T10 priority upgraded mid-way (medium → urgent), answered in time
    at(W(200), s.create("T10", "imran", "Reports page is very slow",
                        "The sales report takes 3 minutes to load.", M))
    at(W(190), s.claim("T10", "Divya"))
    at(W(150), s.priority("T10", "Divya", U))
    at(W(140), s.reply("T10", "Divya", "We found a slow query for large date ranges and are "
                       "deploying a fix. Meanwhile, please run it month by month."))
    # T11 reopened once by the customer (RO-2)
    at(W(2000), s.create("T11", "gayathri", "Barcode labels print blank",
                         "Labels come out blank on our TSC printer.", L))
    at(W(1990), s.claim("T11", "Vikram"))
    at(W(1900), s.reply("T11", "Vikram", "Please set the label size to 50×25 mm in the "
                        "printer driver and try again."))
    at(W(1500), s.resolve("T11", "Vikram"))
    at(W(1000), s.customer_says("T11", "It worked for a day, now blank again."))
    at(W(990), s.note("T11", "Vikram", "Reopened. Check the driver update from last week."))
    # T13 open ticket with notes from two agents
    at(W(500), s.create("T13", "tenzin", "Credit note not reducing the balance",
                        "I created credit note CN-77 but the customer balance did not change.",
                        M))
    at(W(490), s.claim("T13", "Sneha"))
    at(W(480), s.note("T13", "Sneha", "Looks like CN-77 is not linked to the invoice."))
    at(W(470), s.note("T13", "Karthik", "Same thing happened at another customer — link it via "
                      "Adjustments, not Payments."))
    at(W(460), s.reply("T13", "Sneha", "Please open CN-77 → Adjust against invoice and pick the "
                       "invoice. The balance will update."))
    # T14 created by an agent on the customer's behalf (IN-2: phone call)
    at(W(60), s.create("T14", "rohan", "Wants a training session for new staff",
                       "Called in: two new accountants join on Monday, wants a 30-min demo.",
                       L, by="Kavya"))
    at(W(55), s.claim("T14", "Kavya"))
    at(W(50), s.reply("T14", "Kavya", "Happy to help. Would Monday 3 pm work for a call?"))
    # T15 resolved LATE (resolution met after its due time) — appears in the late report
    at(W(1000), s.create("T15", "farhan", "GST return file rejected",
                         "The GSTR-1 JSON is rejected by the portal: 'invalid HSN'.", U))
    at(W(980), s.claim("T15", "Rahul"))
    at(W(950), s.reply("T15", "Rahul", "The HSN for two items has 3 digits; the portal needs 6. "
                       "We are adding a check."))
    at(W(300), s.resolve("T15", "Rahul"))
    # T16 urgent downgraded to low by the lead while still unassigned
    at(W(80), s.create("T16", "lakshmi", "Need last year's invoices as ZIP",
                       "Our auditor needs all FY 2025-26 invoices.", U))
    at(W(20), s.priority("T16", "Meera", L))
    # T17 waiting → customer replied → open again (WAIT-3 resume)
    at(W(900), s.create("T17", "deepa", "Discount not applied on POS",
                        "The 10% festival discount does not apply on the POS screen.", M))
    at(W(890), s.claim("T17", "Priya"))
    at(W(850), s.reply("T17", "Priya", "Is the discount set for 'All outlets' or only the main "
                       "store?", wait=True))
    at(W(500), s.customer_says("T17", "Only the main store. The POS is at our second outlet."))
    at(W(450), s.reply("T17", "Priya", "That is it — edit the scheme and tick the second outlet."))
    # T18 released by one agent and taken by another
    at(W(600), s.create("T18", "neha", "Cannot delete a duplicate customer",
                        "Delete is greyed out for a duplicate customer record.", L))
    at(W(590), s.claim("T18", "Ananya"))
    at(W(580), s.release("T18", "Ananya"))
    at(W(560), s.claim("T18", "Divya"))
    at(W(550), s.reply("T18", "Divya", "It has an invoice attached; merge the two records "
                       "instead via Customers → Merge."))
    # T19 assigned by the lead
    at(W(250), s.create("T19", "manpreet", "SMS alerts stopped",
                        "Customers no longer get the payment SMS.", M))
    at(W(240), s.assign("T19", "Meera", "Arjun"))
    at(W(200), s.reply("T19", "Arjun", "Our SMS provider changed its sender rules; we are "
                       "re-registering your sender id."))
    # T20 new, unassigned, low
    at(W(10), s.create("T20", "imran", "Dark mode?", "Is there a dark mode for the web app?", L))
    # the regular sweep once more at "now"
    at(t.anchor, s.sweep())


def _ensure_agents(factory: sessionmaker[Session], password: str,
                   created_at: datetime) -> dict[str, Agent]:
    """Create the 11 demo accounts (D-044: 2 leads + 9 agents).

    Agents are not ticket data, so a plain insert is fine.
    """
    agents: dict[str, Agent] = {}
    with factory() as session, session.begin():
        accounts = [(lead, AgentRole.lead) for lead in LEADS] + \
            [(agent, AgentRole.agent) for agent in AGENTS]
        for (name, email), role in accounts:
            agent = session.scalars(select(Agent).where(Agent.email == email)).one_or_none()
            if agent is None:
                agent = Agent(email=email, name=name, role=role,
                              password_hash=hash_password(password), created_at=created_at)
                session.add(agent)
                session.flush()
            agents[name.split()[0]] = agent
    return agents


def run(settings: Settings, engine: Engine | None = None) -> SeedReport:
    """Seed the database behind `engine` (default: DATABASE_URL, the restricted app role)."""
    password = settings.seed_demo_password.get_secret_value() \
        if settings.seed_demo_password else ""
    if len(password) < 12:
        raise SeedRefused("set SEED_DEMO_PASSWORD (at least 12 characters) in .env")
    engine = engine or build_engine(settings)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        if session.scalar(select(func.count()).select_from(Ticket)):
            raise SeedRefused("the tickets table is not empty; the seed only runs on a fresh DB")
        anchor: datetime = session.execute(text("SELECT now()")).scalar_one()
        holidays = load_holidays(session)

    agents = _ensure_agents(factory, password, anchor - timedelta(days=60))
    timeline = Timeline(anchor=anchor, holidays=holidays)
    demo = Demo(agents)
    _script(timeline, demo)
    for when, _order, step in sorted(timeline.actions, key=lambda a: (a[0], a[1])):
        with factory() as session, session.begin():
            step(RequestContext(now=when, session=session), holidays)

    with factory() as session:
        result = verify(session)
        counts = Counter(s.value for s in session.scalars(select(Ticket.status)))
    links = {}
    if settings.app_env == "development":
        links = {key: customer_link(settings.public_base_url, token)
                 for key, token in sorted(demo.tokens.items())}
    return SeedReport(verify_ok=result.ok, verify_checked=result.checked,
                      status_counts=dict(sorted(counts.items())), links=links)


def main() -> int:
    """CLI entry point."""
    settings = get_settings()
    try:
        report = run(settings)
    except SeedRefused as refused:
        print(f"seed refused: {refused}", file=sys.stderr)
        return 1
    print(f"audit verify: ok={report.verify_ok} checked={report.verify_checked}")
    print("tickets per status: " + ", ".join(f"{k}={v}" for k, v in
                                             report.status_counts.items()))
    leads = " + ".join(email for _, email in LEADS)
    print(f"accounts: {leads} (leads) + {len(AGENTS)} agents @arvo.example, "
          "password = SEED_DEMO_PASSWORD")
    for key, link in report.links.items():
        print(f"  {key}: {link}")
    return 0 if report.verify_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
