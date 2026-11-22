# Frontdesk

A support-ticket desk for Arvo Systems' 9 support agents and their lead: SLA clocks in working hours, safe ticket claiming, internal notes that never reach the customer, and an audit log you can prove.

[![CI](https://github.com/akshayev/frontdesk/actions/workflows/ci.yml/badge.svg)](https://github.com/akshayev/frontdesk/actions/workflows/ci.yml)

- **Live:** https://frontdesk-qtlh.onrender.com
- **What I did not finish, and why:** [COMPLETION_NOTE.md](COMPLETION_NOTE.md)
- Built for the iNav Technologies Full Stack Developer hiring test (22 Nov 2026).

> The app runs on Render's free plan, which sleeps when idle. If the first page load hangs, wait up to a minute and reload.

## Contents
- [Try it in 5 minutes](#try-it-in-5-minutes)
- [Demo accounts](#demo-accounts)
- [Rules I extracted from the story](#rules-i-extracted-from-the-story)
- [Architecture in brief](#architecture-in-brief)
- [Run locally](#run-locally)
- [Run the tests](#run-the-tests)
- [Deployment notes](#deployment-notes)
- [How it was built](#how-it-was-built)

## Try it in 5 minutes

Use a normal window for agent 1, a private window for agent 2, and a phone or a third window for the customer. Credentials: see [Demo accounts](#demo-accounts).

| # | Do this | You should see |
|---|---|---|
| a | **Be the customer.** Open [/new](https://frontdesk-qtlh.onrender.com/new), submit a problem (pick **medium**). **Copy and save the private link** you get — it is shown once. | The customer page: "Received", your message, exact timestamps. |
| b | **INC-0291 — double claim.** Log in as agent 1 → **Unassigned** → open your ticket. In the private window, log in as agent 2 (a different agent account) and open the same ticket. Put the windows side by side, press **Take this ticket** as agent 1, then straight away as agent 2 (the page refreshes itself within 15 s). | Agent 1 owns the ticket; agent 2 gets **"Already taken by …"** with agent 1's name. Only the assignee can reply, resolve or set waiting. |
| c | **INC-0304 — note leak.** As agent 1, write a **Reply to customer**, tick **"and wait for the customer's answer"** and send. Then switch to **Internal note** (yellow, lock icon) and save a note. Open the customer's private link. | The customer sees the reply and "Waiting for your reply"; the note is **not** there — not on the page, not in the API response. Reply as the customer: the ticket is open again and the paused clock resumes. |
| d | **INC-0318 — "which were late and why".** On the ticket, open **History**: every change, who did it and when (database clock). Log in as a support lead → **Late report** → **Verify audit log**. | The late report lists each late ticket, which target was missed, by how many working minutes, its priority history and the time spent waiting on the customer (CSV export too). Verify says **"Intact — N events checked"** (sha256 hash chain). |
| e | **Meera's open question — priority change mid-way.** As agent 1, change the priority to **urgent** and confirm. Read **History** and the **SLA** panel. | A `priority_changed` event with old/new priority and old/new due times. Resolution is now due at the earlier of the old due and now + 9 working hours; the response target was already met, so it stays met (D-008). |

The seed also contains ~20 tickets in every state (late, at risk, waiting, resolved, closed by both auto-close rules, reopened, a child of a closed ticket).

## Demo accounts

Roles available: **2 support leads** and **9 agents**.

**Credentials are provided in the submission form** — they are not published here (D-047).

**5 wrong passwords lock an account for 15 minutes** (D-029). If a login fails with the right password, use another account of the same role; that is why there are two leads.

The customer side needs no login: use [/new](https://frontdesk-qtlh.onrender.com/new) to submit a problem and get your private link.

## Rules I extracted from the story

"§" = section/paragraph of the hiring-test story. Full rule list with IDs: [docs/PRD.md](docs/PRD.md); reasons and rejected options: [docs/DECISIONS.md](docs/DECISIONS.md).

| Rule as built | From the story | Decision |
|---|---|---|
| Targets in **working minutes** — urgent: first response 2 h, resolution 9 h ("same working day"); medium: 4 h 30 / 3 working days; low: 9 h / 5 working days | §3 ¶1 | D-009 |
| Working time 09:30–18:30 IST, Mon–Fri, minus holidays. Urgent at Fri 18:00 → response due Mon 11:00, never "late" over the weekend | §3 ¶2 | D-009..D-014 |
| Holidays are a lead-editable table, seeded only with 25 Dec 2026 and 26 Jan 2027 (festival dates are not guessed) | §3 ¶2 | D-014 |
| First response = first **public** agent reply (notes never count); resolve needs that reply first | §3 ¶1 | D-027 |
| **Waiting on customer** pauses the resolution clock; entered only with a reply; on the customer's answer the due moves by the waiting time — also for tickets already late | §3 ¶3 | D-025, D-026 |
| Customer silent for **5 working days** ("one working week") → auto-closed by the system | §3 ¶4 | D-010 |
| Customer can reopen a resolved ticket for **7 calendar days** ("about one week"); the clock resumes with the remaining time. After that, writing creates a new linked ticket | §3 ¶5 | D-011, D-012, D-013, D-041 |
| **Priority change mid-way** (Meera's open question): upgrade → earlier of old due and now + new target; downgrade → created + new target minus paused time; met targets stay met; always audited | §3 last ¶ | D-008, D-024 |
| **INC-0291** double claim: atomic claim (`UPDATE … WHERE assignee_id IS NULL RETURNING`), only the assignee acts, every write carries `expected_version` (409 if the ticket changed) | §4.1 | D-020 |
| **INC-0304** note leak: notes in their own table; customer code cannot import it (architecture test); canary test over every customer endpoint, export and preview; distinct yellow note composer | §4.2 | D-022, D-033 |
| **INC-0318** provable history: insert-only audit log (DB triggers + restricted role), sha256 hash chain + verify, database clock | §4.3 | D-015, D-019, D-021 |
| "Which were late and why": lead late report built from tickets + audit events, CSV export | §2 | PRD RPT-1 |

## Architecture in brief

```
Browser — agent/lead SPA (cookie session) · customer page (secret link → X-Ticket-Token header)
   │ same origin, HTTPS
FastAPI (one process) — /api/auth /api/agent /api/lead /api/customer /api/public, /healthz, the built React app
   │ one DB transaction per request, `now` = database clock
PostgreSQL 16 — app connects as restricted role frontdesk_app; migrations run as the owner
```

- **SLA engine** (`backend/app/sla/`): pure functions, no framework, no clock — working-minute maths, priority-change rules, badges.
- **Domain layer** (`backend/app/domain/tickets.py`): every ticket change = lock row → check version → check permission + state machine → apply → version + 1 → audit event, in one transaction.
- **Audit chain** (`backend/app/audit/chain.py`): `audit_events`, `messages` and `internal_notes` are insert-only (triggers + grants); events are hash-chained.
- **Frontend**: React 19 + TypeScript + Vite + Tailwind + TanStack Query, types generated from the backend's OpenAPI schema (CI fails on drift).

Docs: [ARCHITECTURE](docs/ARCHITECTURE.md) · [DECISIONS](docs/DECISIONS.md) · [SECURITY](docs/SECURITY.md) · [TEST-PLAN](docs/TEST-PLAN.md) · [TIMELOG](docs/TIMELOG.md) · [PRD](docs/PRD.md)

**API.** Schema: [/openapi.json](https://frontdesk-qtlh.onrender.com/openapi.json) — load it into any OpenAPI viewer. Swagger UI (`/docs`) runs in development only, because it needs third-party scripts that the production CSP blocks (D-035).

| Group | Endpoints |
|---|---|
| Auth | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` |
| Agent | `GET/POST /api/agent/tickets`, `GET /api/agent/tickets/{id}`, `POST …/{id}/claim`, `…/release`, `…/replies`, `…/notes`, `…/resolve`, `PATCH …/{id}/priority`, `GET …/{id}/transcript.csv` |
| Lead | `GET /api/lead/agents`, `POST /api/lead/tickets/{id}/assign`, `GET /api/lead/reports/late` (+ `.csv`), `GET/POST/DELETE /api/lead/holidays`, `GET /api/lead/audit/verify` |
| Customer | `GET /api/customer/ticket`, `POST /api/customer/ticket/messages`, `POST /api/customer/ticket/reopen` (header `X-Ticket-Token`) |
| Public | `POST /api/public/tickets` |

Writes from the agent app need the header `X-Requested-With: frontdesk` (CSRF). Errors are `{error, message, request_id}`.

## Run locally

**Prerequisites:** Docker with Compose v2 · [uv](https://docs.astral.sh/uv/) (installs Python 3.12 for you) · Node 24 + npm · git, openssl.
Ports 5432 (PostgreSQL) and 8000 (app) must be free.

```sh
git clone https://github.com/akshayev/frontdesk.git
cd frontdesk

# 1. .env from .env.example with fresh random secrets (.env is git-ignored)
PG_PW=$(openssl rand -hex 16); APP_PW=$(openssl rand -hex 16)
sed -e "/^POSTGRES_PASSWORD=/s/<generate-me>/$PG_PW/" \
    -e "/^APP_DB_PASSWORD=/s/<generate-me>/$APP_PW/" \
    -e "s/<APP_DB_PASSWORD>/$APP_PW/" \
    -e "s/<POSTGRES_PASSWORD>/$PG_PW/" \
    -e "/^SESSION_SECRET=/s/<generate-me>/$(openssl rand -hex 32)/" \
    -e "/^SEED_DEMO_PASSWORD=/s/<generate-me>//" \
    .env.example > .env

# 2. PostgreSQL 16 in Docker (waits until it is healthy)
docker compose up -d --wait db

# 3. Backend: dependencies, migrations, demo data
cd backend
uv sync
uv run alembic upgrade head
SEED_DEMO_PASSWORD='local-demo-password' uv run python -m scripts.seed
cd ..

# 4. Frontend build (FastAPI serves frontend/dist)
cd frontend
npm ci
npm run build
cd ..

# 5. Start the app
cd backend
uv run uvicorn app.main:app
```

Open http://localhost:8000 and log in with any account from `LEADS` / `AGENTS` in [backend/scripts/seed.py](backend/scripts/seed.py) (the seed also prints the lead emails) and the password you gave the seed (`local-demo-password` above). Locally the seed also prints a customer link for each demo ticket.

- The seed refuses to run twice (it needs an empty tickets table). To start over: `docker compose down -v` (deletes the local database volume), then repeat from step 2.
- Swagger UI is at http://localhost:8000/docs in development.
- Frontend dev server with hot reload: `cd frontend && npm run dev` (proxies `/api` to :8000).

## Run the tests

With the database from step 2 running:

```sh
cd backend
uv run ruff check .
uv run pytest -q        # unit + integration on real PostgreSQL; creates and drops its own frontdesk_test database
uv run pip-audit
cd ../frontend
npm run check:api       # OpenAPI schema and generated TS types have not drifted
npx tsc -b
npm run lint
npm test                # Vitest
npm audit --omit=dev
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the same on every push, with a PostgreSQL 16 service container.

## Deployment notes

- **Render** (free web service, Singapore, Docker, [render.yaml](render.yaml)) + **Neon** (PostgreSQL 16, aws-ap-southeast-1).
- **Least privilege (D-043):** the web service only gets the `frontdesk_app` `DATABASE_URL` (insert-only on the audit tables), plus `SESSION_SECRET` and `PUBLIC_BASE_URL`. The container never migrates; `alembic upgrade head` and the seed run from the developer machine with the Neon owner role, so a compromised web server cannot disable the audit triggers or change grants.
- **Manual deploys:** the live service is not linked to the Blueprint and pushes have not triggered deploys, so every env var is set by hand in the Render dashboard and deploys are started by hand (dashboard → Manual Deploy, or `render deploys create <service> --commit <sha>`). Check the live commit matches `git rev-parse --short HEAD`.
- **Client IP (D-045, D-046):** Render delivers `X-Forwarded-For: <client>, <Cloudflare edge>, <Render internal>`. `TRUSTED_PROXY_HOPS=3` takes the 3rd entry from the right, which a client cannot forge; it feeds the rate limits and the audit log. Locally it is `0` (socket peer, header ignored). Both earlier versions were found wrong by live tests and fixed — see [SECURITY.md §7–8](docs/SECURITY.md).
- Production: `APP_ENV=production` (HSTS on, `/docs` off), `SWEEP_ENABLED=true` (auto-close sweep every 5 minutes).
- **Uptime:** an UptimeRobot HTTP(s) monitor checks https://frontdesk-qtlh.onrender.com/healthz every 5 minutes, which also keeps the free instance awake. If it does sleep anyway, the first request may take up to a minute.

## How it was built

- Requirements and design first: the story was turned into rules with IDs ([PRD](docs/PRD.md)) and 47 logged decisions ([DECISIONS](docs/DECISIONS.md)), made by me with Claude (claude.ai) as architect and reviewer. Where the story was unclear I decided and wrote down why.
- Code was generated with Claude Code from those specs, sprint by sprint, and I reviewed every sprint against a gate (lint, tests, dependency audit, security checklist) before moving on.
- Real times, including the slow parts, are in [docs/TIMELOG.md](docs/TIMELOG.md).
