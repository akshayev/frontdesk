# Frontdesk — Security

## 1. Threat model (what we protect, from whom)
| Asset | Threat | Control |
|---|---|---|
| Internal notes | Leak to customer via API, list preview, export, event payload, UI | Separate table; separate customer schemas; architecture test forbids imports; canary integration test; payloads reference ids only |
| Audit history | Edit/delete to change "who replied when" | Insert-only grants; mutation + truncate triggers; sha256 hash chain + verify endpoint; DB clock timestamps |
| Ticket ownership | Two agents acting on the same ticket | Atomic claim; row lock + expected_version on every mutation; assignee-only actions |
| Agent accounts | Password guessing | Argon2id; 5/min/IP login limit; DB lockout 15 min after 5 failures; failures audited |
| Agent sessions | Theft via XSS, CSRF | HttpOnly Secure SameSite=Lax cookie; only token hash stored; custom header `X-Requested-With: frontdesk` required on non-GET; strict CSP |
| Customer ticket access | Token guessing, token leakage in logs/referrer | 32-byte random token; hash stored; token in URL fragment, sent in header; 30/min/IP limit; Referrer-Policy no-referrer |
| Secrets | Committed to git | env vars only; `.env` git-ignored; `.env.example` with placeholders |
| Dependencies | Known CVEs | pip-audit and npm audit each sprint and in CI |

## 2. Authentication
- Login: email + password → Argon2id verify (constant-time by library). Same generic error for unknown email and wrong password.
- On success: 32-byte `secrets.token_urlsafe` token; store sha256(token) in `sessions`; cookie `fd_session`; expiry 12 h; logout sets `revoked_at`.
- Lockout: `failed_login_count` ≥ 5 → `locked_until = now + 15 min`; reset on success.

## 3. Authorisation
- Dependencies: `require_agent`, `require_lead`, `require_customer_ticket`.
- Assignee-only actions enforced in domain layer, not only UI.
- Customer token scopes access to exactly one ticket.

## 4. Rate limits (slowapi, in-memory, single instance)
Login 5/min/IP · customer 30/min/IP and public 30/min/IP (separate buckets, D-032) · agent API 120/min/session. Limitation: counters reset on restart and are per-instance (lockout is persistent in DB).

## 5. Headers (middleware)
`Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'` · `X-Frame-Options: DENY` · `X-Content-Type-Options: nosniff` · `Referrer-Policy: no-referrer` · `Strict-Transport-Security: max-age=31536000` (production only).
The CSP is the same on every path. Swagger UI (`/docs`) is served in development only, because it needs third-party scripts. The read-only `/openapi.json` schema is served everywhere (D-035).

## 6. Input and output
- Pydantic validation on every request; subject ≤ 200 chars, bodies ≤ 10 000 chars, emails validated.
- React escapes output; no `dangerouslySetInnerHTML`.
- Errors: no stack traces in production; `{error, message, request_id}`.
- CORS: not enabled (same origin).

## 7. Known limitations (be honest in COMPLETION_NOTE.md)
- Hash chain is tamper-evident, not tamper-proof: a DB superuser could rewrite the whole chain. Next step: publish the head hash outside the DB periodically.
- In-memory rate limits reset on restart.
- IP addresses in the immutable audit log cannot be erased — accepted for security forensics; production would add a retention design. (Login events, D-031; emails are never stored there — actor_id or HMAC only.)
- Demo credentials are published in README for evaluators; a real deployment would force password change.
- Lockout (D-029) can be abused for denial of service: anyone who knows a published demo email can lock that account for 15 minutes. Mitigation for the demo: two lead accounts (D-044). Production would add CAPTCHA / per-IP+account throttling.
- `--forwarded-allow-ips='*'` (uvicorn trusts `X-Forwarded-For` / `-Proto` from any peer) relies on Render's proxy being the only ingress: a Render web service has no public port of its own, every request arrives through Render's TLS proxy, which sets those headers. On any host where the container port is reachable directly, this must become the proxy's address, otherwise clients could spoof their IP (rate limits, audit IPs) and the https scheme.
- No email delivery, so "reply sent" means "recorded in Frontdesk".

## 8. Per-sprint security review checklist
- [ ] No secrets in diff (`git diff | grep -iE "password|secret|key|token"` reviewed)
- [ ] Every new endpoint has an auth dependency and a rate-limit group
- [ ] Every new customer-facing schema checked: no note fields
- [ ] Every mutation goes through domain layer (version check + audit event)
- [ ] pip-audit / npm audit clean or findings noted
- [ ] No raw SQL built with string formatting

### Sprint 2 review (22 Nov 2026)
- [x] No secrets in diff — `git diff | grep -iE "password|secret|key|token"` reviewed (only identifiers, docstrings and the test-fixture password); secret-guard scan clean; Neon URL and app password only in git-ignored `.env.neon`.
- [x] Every new endpoint has an auth dependency and a rate-limit group — `POST /api/auth/login` (public by design; `limit_login` 5/min/IP), `POST /api/auth/logout` and `GET /api/auth/me` (`CurrentAuth`/`CurrentAgent`; `limit_agent` 120/min/session). `/healthz` unchanged (ops, no auth).
- [x] Every new customer-facing schema checked: no note fields — none added; `AgentOut` has no password_hash / lock fields.
- [x] Every mutation goes through domain layer — no ticket mutations this sprint (domain layer is S3). Auth writes (agents lockout fields, sessions) are audited via `append_event`.
- [x] pip-audit / npm audit clean — both "No known vulnerabilities" / "found 0 vulnerabilities".
- [x] No raw SQL built with string formatting — all new SQL is SQLAlchemy constructs or bound parameters.
- [x] Audit payloads checked for personal data — login events carry actor_id or an HMAC of the email, plus IP; never the typed email (D-031).

### Sprint 3 review (22 Nov 2026)
- [x] No secrets in diff — `git diff 1c7e9f2 | grep -iE "password|secret|key|token"` reviewed: only identifiers, docstrings and test fixtures. The seed reads SEED_DEMO_PASSWORD from the environment (placeholder in `.env.example`, ≥ 12 chars enforced). Raw customer tokens are returned once in the response and never stored or logged (the sweep logs counts only).
- [x] Every new endpoint has an auth dependency and a rate-limit group — agent (10 routes): `CurrentAgent` + `limit_agent`; lead (8, incl. `GET /api/lead/agents` — id/name/role only, D-040): `CurrentLead` + `limit_agent`; customer (3): `CustomerTicket` (X-Ticket-Token, 404 otherwise) + `limit_customer`; public (1): no auth by design (IN-1) + `limit_public`. CSRF header enforced by middleware on /api/agent and /api/lead writes.
- [x] Every new customer-facing schema checked: no note fields — `schemas/customer.py` has public message text, "You"/"Support" + agent first name, status, priority and reopen info only: no notes, no agent ids, no SLA dues, no audit events. A-1 (AST + text) and the I-4 canary test enforce it.
- [x] Every mutation goes through domain layer (version check + audit event) — all ticket writes are in `app/domain/tickets.py` (row lock → expected_version → §4 transition → permission → version + 1 → audit event, one transaction); claim is the atomic UPDATE (§7). Holidays go through `app/domain/holidays.py` (audited). The seed uses the domain functions and the sweep only.
- [x] pip-audit / npm audit clean — "No known vulnerabilities found" / "found 0 vulnerabilities".
- [x] No raw SQL built with string formatting — all new SQL is SQLAlchemy constructs; the only `text()` calls are constant strings (`SELECT now()`) and test fixtures with bound parameters.
- [x] CSV exports (transcript, late report) prefix cells starting with = + - @ tab CR with `'` (formula injection); tested.

### Sprint 4 review (22 Nov 2026)
- [x] No secrets in diff — `git diff d8d097c | grep -iE "password|secret|key|token"` reviewed: only identifiers, docstrings, decision text and test fixtures (a fake `secret.txt` for the path-traversal test). Local smoke runs used a throwaway seed password kept outside the repo. secret-guard scan clean before every commit.
- [x] Every new endpoint has an auth dependency and a rate-limit group — no new API endpoint. The SPA catch-all (`app/spa.py`) serves only files from the build directory (no data, no auth needed, traversal-safe, tests S-1..S-4); it never answers `/api/*`, `/healthz/*` or `/openapi.json/*` (JSON 404). Static files have no rate-limit group (nothing to protect; noted).
- [x] Every new customer-facing schema checked: no note fields — no schema change. The customer page renders only `CustomerTicketOut` fields; the agent ticket page never shows the customer link or token.
- [x] Every mutation goes through domain layer (version check + audit event) — no backend mutation added; every UI mutation sends `expected_version` and uses the server's answer (no optimistic updates, D-037); actions are rendered only from `allowed_actions`.
- [x] pip-audit / npm audit clean — "No known vulnerabilities found"; `npm audit --omit=dev` and full `npm audit`: "found 0 vulnerabilities".
- [x] No raw SQL built with string formatting — no new SQL.
- [x] Frontend (D-037, D-038): CSP unchanged and verified in headless Chrome on every screen (no violations, no console errors); no inline `style` props and no `dangerouslySetInnerHTML` (both enforced by oxlint rules); fonts bundled, `assetsInlineLimit: 0` (no `data:` URIs), no third-party origins; message bodies rendered as text (`whitespace-pre-wrap`); `X-Requested-With: frontdesk` on every non-GET (F-2); customer token only in the fragment and the `X-Ticket-Token` header, query keys hold a hash of it; `/login?next=` accepts same-site paths only (no open redirect); `<meta name="referrer" content="no-referrer">` in addition to the header.

### Sprint 5 review (22 Nov 2026)
- [x] No secrets in diff — `git diff | grep -iE "password|secret|key|token"` reviewed: env-var names, docs and the CI database passwords, which are per-run throwaway values (`ci-*-${{ github.run_id }}`) for a service container that lives only for the job; the CI SESSION_SECRET is generated per run with `openssl rand`. Production values (seed password, SESSION_SECRET, app-role URL) exist only in git-ignored `.env.neon` and `DEPLOY-VALUES.local.md` (mode 600) and were never printed. secret-guard scan clean.
- [x] Every new endpoint has an auth dependency and a rate-limit group — no new API endpoint. `HEAD /healthz` (uptime monitors) returns an empty 200 like GET; the SPA catch-all also answers HEAD. `/docs` and `/redoc` are JSON 404 in production (D-035), tested (S-5).
- [x] Every new customer-facing schema checked: no note fields — no schema change.
- [x] Every mutation goes through domain layer — no new mutation. The production seed ran through the domain functions as `frontdesk_app`; `verify()` ok on Neon.
- [x] pip-audit / npm audit clean — run locally and in CI on every push.
- [x] No raw SQL built with string formatting — no new SQL.
- [x] Deploy (D-043): the image has no secrets (`.dockerignore` excludes `.env*`, `*.local.md`, `.git`), runs as non-root uid 10001 with the code read-only, has no uv or build tools, and never migrates; Render receives only the app-role `DATABASE_URL` (Neon direct host, `sslmode=require`; client TLS verified), `SESSION_SECRET`, `PUBLIC_BASE_URL`. CI runs with `permissions: contents: read`. Lockout DoS noted in §7 (D-044).
