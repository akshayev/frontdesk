# Frontdesk — Architecture

## 1. Overview
One Docker service on Render runs FastAPI. FastAPI serves the JSON API under `/api/*` and the built React app for every other path. PostgreSQL 16 on Neon. UptimeRobot pings `/healthz` every 5 minutes.

```
Browser (agent SPA / customer page)
        │  HTTPS, same origin, cookie session (agents) / X-Ticket-Token header (customers)
        ▼
FastAPI (uvicorn, 1 process) ── /api/auth  /api/agent  /api/lead  /api/customer  /api/public  /healthz
        │   SQLAlchemy 2.0 sync, one transaction per request
        ▼
PostgreSQL (Neon) — role frontdesk_app (restricted) ; migrations run as owner role
```

## 2. Repository layout
```
frontdesk/
  CLAUDE.md                 memory brain for Claude Code
  README.md  COMPLETION_NOTE.md
  docs/  PRD.md ARCHITECTURE.md SECURITY.md TEST-PLAN.md DECISIONS.md TIMELOG.md
  docker-compose.yml        local Postgres 16
  Dockerfile  .dockerignore  multi-stage: node build → python runtime (non-root, no migrations — D-043)
  render.yaml               Render Blueprint: one free web service, Singapore, /healthz
  .env.example
  .github/workflows/ci.yml  backend (PG 16 service, ruff, pytest, pip-audit) + frontend (check:api, tsc, lint, vitest, build, npm audit)
  backend/
    pyproject.toml          managed by uv
    alembic.ini  alembic/versions/
    app/
      main.py               app factory, middleware, routers, static SPA mount, lifespan (sweep loop)
      spa.py                serves the built React app (API paths never swallowed, cache rules, D-037)
      config.py             pydantic-settings
      db.py                 engine, session dependency, request "now" from DB
      models.py             SQLAlchemy models
      sla/calendar.py       PURE: working-time maths (no DB, no FastAPI imports)
      sla/policy.py         PURE: targets, priority-change rules, badge computation
      domain/tickets.py     state machine + use cases (claim, reply, note, wait, resolve, reopen, priority), DomainError, allowed_actions
      domain/reports.py     lead late report (RPT-1) built from ticket rows + audit events only
      domain/holidays.py    lead holiday list/add/remove (audited)
      audit/chain.py        append_event(), canonical JSON, hash, verify()
      security/             passwords.py sessions.py csrf.py ratelimit.py headers.py customer_token.py client_ip.py (D-045)
      api/auth.py api/agent.py api/lead.py api/customer.py api/public.py api/health.py (/healthz itself is defined in main.py)
      api/errors.py         DomainError → standard error JSON
      api/csv_export.py     CSV responses with the formula-injection guard (transcript, late report)
      schemas/agent.py      Pydantic response/request models for agent + lead APIs
      schemas/customer.py   Pydantic models for customer + public APIs — MUST NOT import InternalNote
      jobs/sweep.py         auto-close (WAIT-4, RO-3) + the lifespan loop (sweep_once / sweep_loop)
    scripts/seed.py         demo data through the domain functions (`uv run python -m scripts.seed`)
    scripts/export_openapi.py  OpenAPI JSON to stdout (frontend contract, `npm run gen:api`)
    scripts/rotate_demo_password.py  rotate the 11 demo accounts' password + revoke sessions, audited (D-047)
    tests/unit/  tests/integration/  tests/architecture/
                            integration/api_support.py: API test harness (frozen DB time, direct sessions)
  frontend/                 Vite React TS Tailwind TanStack Query
    openapi.json  src/api/schema.d.ts   generated contract (committed; `npm run check:api`)
    src/app src/api src/features/<area> src/components/ui src/lib   (D-037)
```

## 3. Data model (PostgreSQL)
All timestamps `timestamptz`, stored UTC. IDs UUID unless noted.

| Table | Columns (key ones) | Notes |
|---|---|---|
| agents | id, email (unique, lowercased), name, role (`agent`/`lead`), password_hash, failed_login_count, locked_until, created_at | |
| sessions | id, agent_id, token_hash (bytea, unique), created_at, expires_at, revoked_at | token itself never stored |
| customers | id, name, email | |
| tickets | id, number (bigserial, shown as FD-1001), subject, customer_id, priority, status, assignee_id NULL, version int, created_at, first_response_due_at, first_response_at NULL, resolution_due_at, resolution_remaining_min NULL, paused_at NULL, resolved_at NULL, closed_at NULL, close_reason NULL, parent_ticket_id NULL, customer_token_hash (bytea unique), reopen_count | `version` increments on every change |
| messages | id, ticket_id, author_type (`customer`/`agent`), author_agent_id NULL, body (≤10 000 chars), created_at | **public only**; immutable |
| internal_notes | id, ticket_id, agent_id, body (≤10 000 chars), created_at | **agent-only**; immutable |
| audit_events | id bigserial, ticket_id NULL, actor_type (`agent`/`customer`/`system`), actor_id NULL, event_type, payload jsonb, created_at, prev_hash bytea, hash bytea | append-only, hash-chained |
| holidays | date (PK), name, created_by | lead-editable |

Enums: priority (`urgent`,`medium`,`low`); status (`new`,`open`,`waiting_on_customer`,`resolved`,`closed`); close_reason (`no_customer_reply`,`reopen_window_expired`).

Indexes: tickets(status), tickets(assignee_id), tickets(resolution_due_at), messages(ticket_id, created_at), internal_notes(ticket_id), audit_events(ticket_id, id).

DB-level protection (migration, raw SQL):
- Trigger `forbid_mutation()` BEFORE UPDATE OR DELETE on `audit_events`, `messages`, `internal_notes` → RAISE EXCEPTION.
- BEFORE TRUNCATE trigger on the same tables.
- Role `frontdesk_app`: SELECT/INSERT on those three tables only; SELECT/INSERT/UPDATE on tickets, agents, sessions, customers, holidays (DELETE only on holidays and sessions). Owner role runs migrations. (Verified on Neon in Sprint 2 — D-015: PostgreSQL 16.16, aws-ap-southeast-1; CREATE ROLE accepted; frontdesk_app has no elevated attributes and is a member of no role; grants and triggers behave as locally. As standard in PG16, the creating role `neondb_owner` holds ADMIN on frontdesk_app — this gives frontdesk_app nothing.)

## 4. State machine
| From | Action | Actor | To |
|---|---|---|---|
| new | claim | agent | open (assignee = agent) |
| open (unassigned) | claim | agent | open |
| open | release | assignee | open (unassigned) |
| any non-closed | assign | lead | same status, new assignee |
| open | reply | assignee | open |
| open | reply + wait | assignee | waiting_on_customer (pause) |
| waiting_on_customer | customer reply | customer | open (resume) |
| open | resolve | assignee | resolved |
| resolved (≤7 days) | customer reopen / customer reply | customer | open (resume) |
| waiting_on_customer (5 working days silent) | sweep | system | closed (no_customer_reply) |
| resolved (>7 days) | sweep | system | closed (reopen_window_expired) |
| resolved (>7 days) | customer writes | customer | old → closed (reopen_window_expired) + new ticket, parent_ticket_id = old, same transaction (D-041) |
| closed | customer writes | customer | new ticket, parent_ticket_id = old |
| new/open/waiting | change priority | assignee or lead | same |

Anything not in this table → HTTP 409 `illegal_transition`.

## 5. SLA engine (pure functions, `app/sla/`)
- `add_working_minutes(start: datetime, minutes: int, holidays: frozenset[date]) -> datetime`
- `working_minutes_between(a: datetime, b: datetime, holidays) -> int` (negative if b < a)
- Calendar constants: TZ=Asia/Kolkata, open 09:30, close 18:30, weekdays Mon–Fri.
- If `start` is outside working time, counting begins at the next working opening.
- `policy.targets(priority) -> (response_min, resolution_min)`
- `policy.apply_priority_change(ticket_snapshot, new_priority, now, holidays) -> new due values` (PRI-1..4)
- `policy.badge(ticket_snapshot, now, holidays) -> {state: late|at_risk|paused|on_track|met, minutes_left|minutes_overdue}`
- No module in `app/sla/` may import FastAPI, SQLAlchemy or read the system clock.

## 6. Time source
At the start of each request transaction the app runs `SELECT now()` and uses that single value as `now` for all domain logic and audit events in that request. Tests override it. The Python system clock is never used for business logic.

## 7. Concurrency
- Claim: `UPDATE tickets SET assignee_id=:me, status='open', version=version+1 WHERE id=:id AND assignee_id IS NULL AND status IN ('new','open') RETURNING *`. 0 rows → 409 with current owner.
- All other mutations: `SELECT … FOR UPDATE` the ticket row, check `version == expected_version` (else 409 `stale_version`), check permission and transition, apply, `version += 1`, append audit event, commit.

## 8. Audit chain (`app/audit/chain.py`)
- `append_event(session, now, ticket_id, actor_type, actor_id, event_type, payload)`:
  1. `SELECT pg_advisory_xact_lock(<fixed key>)` (serialises chain appends; released at commit)
  2. read latest `hash` (or 32 zero bytes)
  3. canonical = JSON of {ticket_id, actor_type, actor_id, event_type, payload, created_at ISO-8601 UTC with microseconds}, `sort_keys=True, separators=(",", ":")`
  4. `hash = sha256(prev_hash + canonical_bytes)`; insert row with `created_at = now`.
- `verify(session) -> {ok: bool, checked: int, first_bad_id: int|None}` recomputes in id order.
- Event types: ticket_created, claimed, released, assigned, customer_message, agent_reply, note_added, status_changed, priority_changed, resolved, reopened, auto_closed (actor system from the sweep, or customer when a write after the reopen window closes the ticket, D-041), holiday_added, holiday_removed, login_succeeded, login_failed, account_locked, password_rotated (actor system, payload `{agent_id}` only — `scripts/rotate_demo_password.py`, D-047).
- Payloads never contain note bodies (LEAK-3). Message events contain message_id only.

## 9. Background sweep (`app/jobs/sweep.py`)
Runs in a lifespan asyncio loop every 5 minutes and once at startup; idempotent. Closes WAIT-4 and RO-3 tickets with actor `system`. SLA badges never depend on it (computed at read time).

## 10. API surface
Auth: `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
Agent: `GET /api/agent/tickets?view=mine|unassigned|all|late|waiting`, `POST /api/agent/tickets`, `GET /api/agent/tickets/{id}`, `POST …/{id}/claim`, `POST …/{id}/release`, `POST …/{id}/replies` {body, expected_version, wait_for_customer}, `POST …/{id}/notes` {body, expected_version}, `POST …/{id}/resolve` {expected_version}, `PATCH …/{id}/priority` {priority, expected_version}, `GET …/{id}/transcript.csv` (public messages only; `text/csv` in the OpenAPI schema, like `late.csv`)
Lead: `GET /api/lead/agents` ({id, name, role} only, no emails — D-040), `POST /api/lead/tickets/{id}/assign`, `GET /api/lead/reports/late` (+ `.csv`), `GET/POST/DELETE /api/lead/holidays`, `GET /api/lead/audit/verify`
Customer (header `X-Ticket-Token`): `GET /api/customer/ticket`, `POST /api/customer/ticket/messages`, `POST /api/customer/ticket/reopen`
Public: `POST /api/public/tickets` (returns secret link once)
Ops: `GET /healthz`

Errors: JSON `{error: code, message, request_id}`; codes include `stale_version`, `already_claimed`, `illegal_transition`, `forbidden`, `rate_limited`, `validation_error`.

## 11. Frontend routes
`/` (redirect by session), `/login`, `/tickets` (list), `/tickets/:id`, `/reports/late` (lead), `/holidays` (lead), `/new` (public submit), `/t` (customer view; token read from `location.hash` on every load and sent as `X-Ticket-Token`; it stays in the fragment so refresh and bookmarks keep working — D-038 supersedes the earlier `history.replaceState` plan), `*` → not found. Lazy route chunks; guards via `GET /api/auth/me`; architecture in D-037.
Serving (`app/spa.py`): API routes win; unknown `/api/*` → JSON 404 for every method (a known API path with the wrong method → 405 + `Allow`); `/assets/*` → `Cache-Control: public, max-age=31536000, immutable`; any other GET → `index.html` with `no-cache`; HEAD is answered like GET without a body (uptime monitors), also on `/healthz`; `/docs` and `/redoc` → JSON 404 when Swagger is off (production, D-035). The CSP is the same as on every response.

## 12. Deployment
Dockerfile stage 1 `node:24-slim` builds `frontend/dist`; stage 2 `python:3.12-slim` installs the backend with uv (`uv sync --frozen --no-dev`), copies dist to `app/static`, runs as a non-root user and starts only `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}` — no `--proxy-headers` / `--forwarded-allow-ips`, so uvicorn never rewrites the client address (D-045).
**The container never migrates (D-043).** `alembic upgrade head` and `scripts/seed.py` run from the developer machine with the Neon owner role (`.env.neon`); the web service only has the `frontdesk_app` URL, so a compromised web server cannot disable the audit triggers or change grants.
Env on Render (web service, `render.yaml`): `DATABASE_URL` (frontdesk_app role, Neon direct host, `sslmode=require`), `SESSION_SECRET`, `PUBLIC_BASE_URL` (all `sync: false`, entered in the dashboard), `APP_ENV=production`, `SWEEP_ENABLED=true`, `TRUSTED_PROXY_HOPS=3` (D-046).
**Render setup.** The live service (`frontdesk`, `srv-dc19n6jl550s73dskekg`) is not linked to the Blueprint (its first deploy shows `blueprint_sync`, but no blueprint is linked now); `render.yaml` documents the intended config, so every env var (including a new one such as `TRUSTED_PROXY_HOPS`) is set by hand in the dashboard. Deploys may need a manual trigger: auto-deploy is on (trigger: commit, branch `main`) but pushes have not started deploys, so use dashboard → Manual Deploy or `render deploys create srv-dc19n6jl550s73dskekg --commit <sha>`, then check the live commit matches `git rev-parse --short HEAD` (D-045 implementation notes).
**Client IP (D-045, D-046).** `app/security/client_ip.py` is the only code that reads `X-Forwarded-For` (or `CF-Connecting-IP`, the raw peer); it feeds every rate-limit key and the IP in audit events. `TRUSTED_PROXY_HOPS=N` is the position from the right of the client entry: `3` on Render, which delivers `<client>, <Cloudflare edge>, <Render internal 10.x>`; clients can only prepend entries, so it cannot be forged. `0` (default; development, tests): the socket peer, header ignored. A missing, short or malformed header falls back to the peer, never to a client-supplied value. Tripwire: a chosen IP that differs from `CF-Connecting-IP` logs one WARNING without IP values ("client-ip mismatch: proxy chain may have changed"); `CF-Connecting-IP` is compared, never used. A DEBUG line describes the header shape on a fallback or non-global entry.
Developer machine only: `MIGRATION_DATABASE_URL` (owner), `APP_DB_PASSWORD` (used by migration 0003 to create the app role), `SEED_DEMO_PASSWORD`.
