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

---

## Incident → design map (interview)
- INC-0291 → atomic claim UPDATE … WHERE assignee_id IS NULL RETURNING (409) + assignee-only actions + expected_version (D-020).
- INC-0304 → separate table, separate customer schemas, public-only previews/exports, canary + architecture tests (D-022).
- INC-0318 → audit_events append-only, triggers, restricted role, hash chain, DB clock (D-015, D-019, D-021).
- "Which were late and why" → lead late report from events.

## Tooling (verified 22 Nov 2026)
Render CLI `render` (official) · Neon CLI `neon`/`neonctl` (npm) · UptimeRobot CLI `@uptimerobot/cli` (official, free plan) · git, gh, docker compose, uv, alembic, pytest, ruff, pip-audit, npm.
