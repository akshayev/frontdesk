# Frontdesk — Decision Log (iNav / Coligo machine test)

Project: Frontdesk support system for "Arvo Systems" (iNav Technologies Full Stack Developer machine test)
Owner: Akshay E V · Architect/reviewer: Claude · Builder: Claude Code
Deadline: Mon 23 Nov 2026, before 12:00 PM IST
Format per entry: ID · timestamp (IST, 22 Nov 2026 unless stated) · decision · why · rejected options · interview line.
Rule: never change an entry silently. Superseding = new entry that references the old ID.

---

## D-001 · 10:11 · Backend = Python + FastAPI
- Why: author strongest in Python, JS beginner; test allows Node or Python; every line must be explainable. Pydantic response models (structural note-leak fix), dependency guards for roles, auto /docs.
- Rejected: NestJS (many new concepts, unfamiliar language, 26-h deadline); Express/Fastify (still JS → explainability risk).
- Trade-off: lose "matches their NodeJS stack" signal.

## D-002 · 10:15 · Data layer = SQLAlchemy 2.0 (sync) + Alembic
- Why: with_for_update() and update().where().returning() for atomic claim; Alembic holds raw SQL for triggers/grants. Sync: 40 tickets/day, correctness comes from DB transactions.
- Rejected: SQLModel (DB model = API schema → easy to leak notes); raw psycopg (boilerplate); Django ORM (framework switch, admin can edit immutable rows).

## D-003 · 10:15 · Database = PostgreSQL (not MySQL)
- Why: UPDATE … RETURNING (single-statement atomic claim), transactional DDL, timestamptz, JSONB, free Neon hosting.
- Rejected: MySQL — no UPDATE…RETURNING, non-transactional DDL, weaker timezone types.

## D-004 · 10:15 · Frontend = React + Vite + TS + Tailwind + TanStack Query, served by FastAPI (same origin)
- Rejected: Next.js (SSR unneeded); Angular (too heavy to learn now); Jinja+HTMX (dated look).
- Honesty: frontend built with Claude's help; author's focus is backend + domain rules.

## D-005 · 10:18 · Auth = server-side sessions, hashed token, HttpOnly Secure SameSite=Lax cookie + required custom header on writes
- Rejected: JWT cookie (no instant revocation); JWT localStorage (XSS-stealable); no-password dropdown (defeats "who did it").
- Customers: per-ticket secret link token, hash stored, one-ticket scope.

## D-006 · 10:18 · Roles = agent + lead

## D-007 · 10:20 · Hosting = Render free (Docker) + Neon free Postgres + UptimeRobot 5-min ping
- Render free sleeps after ~15 min idle → ping. SLA computed at read time; sweep in-process.
- Rejected: Railway (trial credit then paid), Fly.io (free terms uncertain), EC2 (infra time).

## D-008 · 10:21 · Priority change mid-ticket
- Upgrade: new due = min(old due, change time + new target). Downgrade: created_at + new target excluding paused time. Met targets stay met. Audited.
- Example: Medium created Mon 10:00 (response due 14:30). → Urgent at 10:30 ⇒ 12:30. → Urgent at 13:00 ⇒ 14:30.
- Rejected: recompute from creation (instant fake breach), uncapped restart (escalation buys time), ignore (urgent meaningless).

## D-009..D-014 · 10:21 · SLA interpretations
| ID | Rule | Decision | Reason |
|---|---|---|---|
| D-009 | Urgent "fix same working day" | 540 working min | literal reading gives an 18:15 ticket 15 minutes |
| D-010 | Auto-close on silence | 5 working days | "one *working* week" |
| D-011 | Reopen window | 7 calendar days | "about one week" (no "working") |
| D-012 | Writes after window | new ticket, parent_ticket_id | "after that it is a new ticket" |
| D-013 | Reopen | resolution clock resumes with remaining minutes | problem not fixed |
| D-014 | Holidays | lead-editable table, seeded only with 2026-12-25 and 2027-01-26 | festival dates vary yearly; not guessed |
Targets (working min): urgent 120/540 · medium 270/1620 · low 540/2700. Calendar 09:30–18:30 IST Mon–Fri minus holidays.

## D-015 · 10:24 · Audit = append-only + mutation/truncate triggers + restricted app role + global sha256 hash chain + verify endpoint
- Limitation: tamper-evident, not tamper-proof (superuser can rewrite chain). Verify Neon CREATE ROLE in Sprint 1.
- Rejected: trigger only, app-only, full event sourcing.

## D-016 · 10:25 · Rate limiting = slowapi in-memory (login 5/min/IP, customer 30/min/IP, agent 120/min/session) + DB login lockout (5 fails → 15 min)
- Rejected: Redis (extra service), per-request DB counters, none.

## D-017 · 10:25 · Security baseline: Argon2id; customer token in URL fragment → header, hashed; CSP/XFO/nosniff/Referrer-Policy/HSTS; Pydantic max lengths; no CORS; generic errors + request id; env secrets; pip-audit + npm audit.

## D-018 · 10:28 · Testing = pytest on real Postgres + GitHub Actions (ruff, pytest, pip-audit); frontend type-check + build only.
- Rejected: unit-only (SQLite can't reproduce row locks), Playwright (time), manual.

## D-019 · 10:45 · Audit table named `audit_events` (refines D-015)
- Why: auth events (login failed, account locked) and holiday changes must also be audited, and they have no ticket. `ticket_id` is nullable.

## D-020 · 10:45 · Stale-write protection uses `tickets.version` + `expected_version` (refines the INC-0291 design)
- Every mutation: SELECT … FOR UPDATE, compare version, else 409 stale_version; version += 1. Replaces the earlier `last_seen_event_id` idea — same guarantee, simpler, one integer.

## D-021 · 10:45 · Single time source = database `now()` per request transaction
- Domain logic and audit timestamps use one `SELECT now()` value per request; the Python clock is never used for business rules. Tests inject time. Prevents app/DB clock drift in the evidence record.

## D-022 · 10:45 · Internal notes in a separate table + architecture test
- `internal_notes` separate from `messages`; customer schema/API modules must not import it (tests/architecture A-1); audit payloads reference ids, never note bodies.

## D-023 · S1 · App DB role and its password
- App DB role password comes from env `APP_DB_PASSWORD`. Migration creates role `frontdesk_app` (LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT) if missing. The password is passed with `SELECT set_config('fd.app_pw', :pw, true)` and used inside a DO block via `format('... PASSWORD %L', current_setting('fd.app_pw'))` — never string-formatted in Python. Migrations run as the owner role; the app connects as `frontdesk_app`.

## D-024 · S1 · One formula for downgrade and paused priority changes
- Downgrade and paused priority changes use one formula: `remaining_new = new_target − (old_target − remaining_now)`; `due = now + remaining_new` (if not paused). Equivalent to "created_at + new_target excluding paused time" with no extra column.
- Computed as old_due + (new_target − old_target) working minutes (same value, avoids an 18:30/09:30 edge).

## D-025 · S1 · SLA badge semantics and window boundaries (approved by owner during S1)
- **Late is sticky.** `badge()`: once any target is missed, badge = `late` with target = the missed one and minutes = how late; if both were missed, show resolution. Otherwise the response target is shown until it is met, then resolution. Matches SLA-7 and keeps the "Late" view consistent with the badge.
- **SLA panel shows both targets.** The ticket detail SLA panel (UI-4) shows response and resolution separately (due, met_at, state), so agents still see the resolution countdown on a late ticket (`policy.target_statuses()`).
- **Late wins over paused, overdue minutes freeze.** A `waiting_on_customer` ticket whose resolution was already overdue at pause (WAIT-3 breach preserved) shows `late`, with minutes = `working_minutes_between(resolution_due_at, paused_at)` — frozen at the pause, not counted up to now, because customer waiting time is not Arvo's fault (Meera, Section 3). The list row still shows status "Waiting on customer" separately. Test U-21.
- **Boundary convention: a window ends AT the boundary (>=).** Auto-close (WAIT-4) when `working_minutes_between(paused_at, now) >= 2700`. Reopen (RO-1/RO-2) allowed only while `now − resolved_at < 7 days`; the sweep (RO-3) closes when `now − resolved_at >= 7 days`. The exact 7-day instant belongs to "expired". U-19, U-20.
- Rejected: badge follows only the currently shown target (Late view would disagree with the badge); paused always wins (hides a real breach); overdue minutes keep growing while paused (blames the team for customer silence); `>` boundaries (two conventions in one system).

## D-026 · S2 · Resume and reopen exclude waiting/resolved time for every ticket (approved by owner, Sprint 2)
- On resume (customer reply to waiting) and on reopen, due = add_working_minutes(old_due, working_minutes_between(paused_at or resolved_at, now)). Customer-waiting and resolved time are excluded for breached tickets too; for on-time tickets this equals now + remaining. Supersedes the 'keep old due when remaining = 0' part of WAIT-3.
- Implemented in `policy.resume()`. `resolution_remaining_min` is kept only for the paused badge and PRI-4 (`change_priority` while paused); a priority change while paused moves the preserved due by the same delta, so resume still lands on now + new remaining.
- Why: with "keep old due", a ticket 30 min late at pause became late by 30 min + the whole waiting time on resume — blaming the team for customer silence, contradicting D-025's frozen overdue minutes.
- Rejected: keep old due (above); reset the clock on resume (hides a real breach).

## D-027 · S2 · Resolve requires a met first response (approved by owner, Sprint 2)
- Resolve requires a met first response (at least one public agent reply); otherwise 409 reply_required.
- Noted in PRD SLA-6; enforced in the domain layer in Sprint 3.
- Why: resolving without ever answering the customer would leave the response target unmet forever on a closed-out ticket and makes "met" meaningless.

## D-028 · S2 · httpx2 not added
- httpx2 not added — unverified package taken from a warning text (typosquatting risk). The single StarletteDeprecationWarning is filtered by exact message in pytest config.
- Why: CLAUDE.md requires approval for new dependencies; a package name suggested only by a runtime warning is not a trustworthy source.

## D-029 · S2 · Login failures are indistinguishable (approved by owner, Sprint 2)
- Login always returns 401 with one generic message ('Invalid email or password, or the account is temporarily locked') for unknown email, wrong password and locked account — no account enumeration. Lockout (5 failures → locked_until = now + 15 min) and every failure/lock are audited (login_failed, account_locked, login_succeeded). Supersedes '423' in TEST-PLAN I-12.
- Implementation notes: a full Argon2 verification runs on every path (dummy hash for unknown emails) so timing is equal too; attempts while locked are audited as login_failed (reason "locked") and do not extend the lock; the failure count resets only on success (SECURITY §2). The 401 is returned, not raised, so the request transaction commits the counter and the audit events.
- Rejected: 423 for locked accounts (tells an attacker the email exists and that guessing is working).

## D-030 · S3 · Responsive UI, mobile-first on every screen (approved by owner, Sprint 3; implemented in S4)
- Customer pages are phone-first (links arrive via WhatsApp). Agent/lead pages are desktop-first but fully usable on phones.
- Reply vs note: distinct colours (blue = reply to customer, yellow = internal note) AND distinct button labels on every screen size; note mode is never hidden in a menu.
- Rules: no horizontal scroll at 360 px; tap targets ≥ 44 px; inputs ≥ 16 px (no iOS zoom); badges use colour + text; the composer stays visible with the on-screen keyboard open.
- Verification: manual DevTools check at 360×800, 768×1024, 1440×900, plus a real phone after deploy.
- Why: customers open the secret link from WhatsApp on a phone; agents sometimes answer from a phone. INC-0304 shows what happens when the two composers look alike.

## D-031 · S2 · Login audit events never store the typed email (approved by owner, Sprint 2; refines D-029)
- Known account → record actor_id (the agent's id) and no email. Unknown email → record a keyed hash, HMAC-SHA256 with SESSION_SECRET of the lower-cased email (`email_hmac`), never the raw text. The client IP is kept (needed to investigate attacks).
- Why: people often type their password into the email field; the audit log is insert-only by design (D-015), so anything written there is kept forever and can never be corrected or erased. The DPDP Act expects personal data to be kept only as long as needed, which an undeletable log cannot honour. The keyed hash still shows repeated attacks on the same address, while a mistyped password is unreadable. A plain (unkeyed) hash would be reversible by guessing common emails/passwords.
- Consequence: rotating SESSION_SECRET means hashes before and after the rotation can no longer be matched to each other (acceptable; old events stay verifiable because the hash is just payload data).
- Rejected: store the raw email (above); store nothing for unknown emails (hides targeted attacks).

## D-032 · S2 · Customer and public rate limits are separate buckets (approved by owner, Sprint 2)
- `/api/customer` and `/api/public` each have their own 30/min/IP bucket (slowapi shared scopes "customer" and "public").
- Why: they are different actions (reading/replying on one's own ticket vs. submitting a new one). The customer page polling every 30 s uses 2 requests/min, well inside either limit; a shared bucket adds nothing.

## D-034 · S3 · Agent list views: active-only except All; active tickets always sort first (approved by owner, Sprint 3)
- Mine = assigned to me and new/open/waiting_on_customer/resolved. Unassigned = unassigned and new/open. Late = badge `late` and status new/open/waiting_on_customer. Waiting = waiting_on_customer. All = every status, including resolved and closed. Every view is capped at 200 rows.
- Sort: active tickets (new/open/waiting) first — late first (most overdue), then nearest due — then resolved/closed tickets by most recent activity. So the 200 cap never hides an active ticket behind old closed ones.
- Why: late is sticky (D-025), so counting resolved/closed tickets would turn the Late view into a history list; the lead's late report (RPT-1) is the place for history.
- Rejected: no status filters (Late and Mine fill up with history); hiding closed tickets everywhere (All would no longer be "all").

## D-035 · S3 · /openapi.json served in production; Swagger UI (/docs) development only (approved by owner, Sprint 3)
- `/openapi.json` (read-only schema, no secrets) is served in every environment so evaluators can load it into any OpenAPI viewer; the README will link it and list the endpoints. `/docs` (Swagger UI) stays on in development only.
- Why: Swagger UI loads JS/CSS from a third-party CDN and runs an inline script, so production would need a weaker CSP. No third-party scripts on our origin, and SECURITY §5 stays as it is.
- Rejected: relaxing the CSP on /docs only; turning /docs on under the strict CSP (the page would render blank).
- (D-033 is reserved for the UI-pattern research that will be added in Sprint 4.)

---

## Incident → design map (interview)
- INC-0291 → atomic claim UPDATE … WHERE assignee_id IS NULL RETURNING (409) + assignee-only actions + expected_version (D-020).
- INC-0304 → separate table, separate customer schemas, public-only previews/exports, canary + architecture tests (D-022).
- INC-0318 → audit_events append-only, triggers, restricted role, hash chain, DB clock (D-015, D-019, D-021).
- "Which were late and why" → lead late report from events.

## Tooling (verified 22 Nov 2026)
Render CLI `render` (official) · Neon CLI `neon`/`neonctl` (npm) · UptimeRobot CLI `@uptimerobot/cli` (official, free plan) · git, gh, docker compose, uv, alembic, pytest, ruff, pip-audit, npm.
