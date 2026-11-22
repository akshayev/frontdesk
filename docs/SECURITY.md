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
- `--forwarded-allow-ips='*'` relies on Render's proxy being the only ingress.
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
