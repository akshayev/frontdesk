# CLAUDE.md — Frontdesk memory brain

You are building **Frontdesk**, a support-ticket system for the iNav Technologies hiring test.
The specs are FINAL and live in `docs/`. Read them before coding. Do not invent requirements.

## Source of truth (read in this order)
1. docs/PRD.md — rules with IDs (SLA-*, WAIT-*, RO-*, PRI-*, UI-*, CLM-*, LEAK-*, AUD-*, RPT-*, IN-*)
2. docs/ARCHITECTURE.md — layout, schema, state machine, API, SLA engine, audit chain
3. docs/SECURITY.md — controls and per-sprint checklist
4. docs/TEST-PLAN.md — test IDs that must exist and pass
5. docs/DECISIONS.md — why things are the way they are (D-001…)
If a spec is ambiguous or conflicts: STOP and ask. Never guess silently. Never change a decision without the user approving a new D-entry.

## Stack (fixed)
Python 3.12 · FastAPI · SQLAlchemy 2.0 sync · Alembic · PostgreSQL 16 · psycopg 3 · Pydantic v2 · slowapi · argon2-cffi · pytest · ruff · uv
Frontend: React + Vite + TypeScript + Tailwind + TanStack Query (served by FastAPI from app/static)
Infra: Docker, docker compose (local DB), Render (web), Neon (DB), UptimeRobot, GitHub Actions

## Non-negotiable rules
- Note bodies (`internal_notes`) never reach customer code: `app/schemas/customer.py`, `app/api/customer.py`, `app/api/public.py` must not import or query it. List previews and exports use `messages` only.
- `audit_events`, `messages`, `internal_notes` are insert-only. Never write UPDATE/DELETE for them.
- Every ticket mutation goes through `app/domain/tickets.py`: lock row (FOR UPDATE) → check expected_version → check permission + state machine → apply → version+1 → append audit event → same transaction.
- Use the request's DB `now` (ARCHITECTURE §6). Never call `datetime.now()` / `utcnow()` in business logic or `app/sla/`.
- `app/sla/` is pure Python: no FastAPI, no SQLAlchemy, no clock.
- All SQL through SQLAlchemy constructs or bound parameters. No string-formatted SQL.
- Secrets only from environment. Never print connection strings or keys to the terminal, logs or chat. Write them only to `.env` (git-ignored).
- Python: type hints everywhere, small functions, docstrings on domain/SLA/audit functions explaining the rule ID they implement.

## Commands
- Local DB: `docker compose up -d db`
- Backend: `cd backend && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --reload`
- Tests: `cd backend && uv run pytest -q` · Lint: `uv run ruff check .` · Audit: `uv run pip-audit`
- Frontend: `cd frontend && npm ci && npm run build` (dev: `npm run dev`, proxies /api to :8000)

## Ask the user before
- Any delete of cloud resources (`neon projects delete`, `render services delete`), `git push --force`, `DROP`, rewriting git history.
- Adding a dependency not listed above.
- Any deviation from docs/.

## After every sprint
1. Run the sprint gate in docs/TEST-PLAN.md and paste the results.
2. Append a row to docs/TIMELOG.md (start, end, what was done) — use real times from `date`.
3. Commit with a clear message. Summarise: files changed, tests run + results, anything NOT done, any open question.
