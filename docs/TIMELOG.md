# Frontdesk — Time Log

Honest record of time spent. All times IST (UTC+05:30). Deadline: Mon 23 Nov 2026 12:00.

| Sprint | Start | End | Duration | What was done | Notes |
|---|---|---|---|---|---|
| Planning | 2026-11-22 09:42 | 2026-11-22 10:32 | 50 min | Read brief, researched company, 18 decisions (docs/DECISIONS.md) | With Claude as architect reviewer |
| S0 Scaffold | 2026-11-22 10:40 | 2026-11-22 10:43 | 3 min | Repo, docker-compose db, backend (uv, layout §2, alembic init, healthz), frontend (Vite+React+Tailwind v4+TanStack Query) | Gate passed; all tools pre-installed |
| S1 Schema + SLA engine | 2026-11-22 10:49 | 2026-11-22 11:06 | 17 min | Part A: models, 4 hand-written migrations (schema, insert-only triggers, frontdesk_app role + exact grants, holiday seed), I-5/I-6 + grant/round-trip/drift tests. Part B: pure SLA calendar + policy (PRI/WAIT/RO rules, badge), U-1..U-21, A-2. D-023, D-024, D-025 | Badge/boundary questions answered by owner → D-025. 93 tests green |
| S2 Plumbing + audit + auth | 2026-11-22 11:21 | 2026-11-22 11:39 | 18 min | Part 0: D-026 resume/reopen excludes waiting time, D-027, D-028, warning filter. Part 1: Neon check (PG 16.16, ap-southeast-1, role + grants + triggers verified, schema migrated). Part 2: request transaction + DB clock, hash-chained audit log + verify. Part 3: Argon2 login, sessions, lockout (D-029), CSRF, rate limits, security headers, error format. Follow-up: D-031 (no typed email in login audit), D-032 | Gate passed: ruff clean, 130 tests 0 warnings, pip-audit + npm audit clean |
| S3 Domain + API | 2026-11-22 11:40 | 2026-11-22 12:05 | 25 min | Part 0: D-030 (responsive UI), SECURITY §7 IP wording (D-031/D-032 code already in 4a55f4f). Part A: domain state machine + use cases, DomainError, sweep. Part B: agent/lead/customer/public APIs, separate schemas, CSV guard, late report, D-034 list views, D-035 openapi.json in prod. Part C: lifespan sweep loop, demo seed through domain functions. Part D: I-1/2/3/4/8/9/10/11/14, D-027, PRI-5, RPT-1, workflow + verify, A-1, seed test | Owner answered list-view and Swagger questions → D-034, D-035. Gate: ruff clean, 180 tests 0 warnings, pip-audit + npm audit clean. Follow-up 12:03–12:05: D-040 `GET /api/lead/agents`, D-041 immediate close of the old ticket on a write after the window, ARCHITECTURE §2/§4/§8/§10 synced; 182 tests |
| S4 Frontend | | | | | |
| S5 Deploy + CI | | | | | |
| S6 Docs | | | | | |

Tooling disclosure: design decisions made with Claude (claude.ai) as reviewer; code generated with Claude Code from these specs and reviewed each sprint.
