# Frontdesk — Test Plan

All tests run with `uv run pytest`. Integration tests use real PostgreSQL 16 (docker compose locally, service container in CI). SQLite is never used.

## Unit — SLA engine (`tests/unit/test_calendar.py`, `test_policy.py`)
| ID | Case | Expected |
|---|---|---|
| U-1 | Urgent created Fri 18:00 IST, 120 min | due Mon 11:00 IST |
| U-2 | Created Sat 10:00, 60 min | due Mon 10:30 |
| U-3 | Created 08:00 Tue, 30 min | due Tue 10:00 |
| U-4 | Created 18:30 exactly Wed, 1 min | due Thu 09:31 |
| U-5 | Holiday Fri 25 Dec 2026; created Thu 24 Dec 18:00, 60 min | due Mon 28 Dec 10:00 |
| U-6 | working_minutes_between Fri 17:30 → Mon 10:30 | 120 |
| U-7 | working_minutes_between reversed | negative |
| U-8 | Medium resolution 1620 from Mon 09:30 | Wed 18:30 |
| U-9 | Low resolution 2700 from Mon 09:30 | Fri 18:30 |
| U-10 | Upgrade medium→urgent at Mon 10:30 (created Mon 10:00) | response due 12:30 |
| U-11 | Upgrade medium→urgent at Mon 13:00 | response due stays 14:30 |
| U-12 | Downgrade urgent→low | due = created + 540 working min |
| U-13 | Upgrade when response already met | response unchanged |
| U-14 | Priority change while paused | remaining adjusted per PRI-4 |
| U-15 | Pause/resume preserves remaining minutes | due shifted correctly |
| U-16 | Pause when already overdue | old due kept while paused; on resume due shifts by the waiting time (D-026: late 30 at pause → 2 working days → resume → +60 → late 90) |
| U-17 | Badge at_risk threshold 25% | at_risk |
| U-18 | Badge late / met / paused | correct state |
| U-19 | 5 working days auto-close boundary | closes at exactly 2700 working min and after, not before (D-025 `>=`) |
| U-20 | 7 calendar days reopen boundary | allowed at 6d23h, refused at exactly 7d (D-025) and at 7d+1s |
| U-21 | Paused when already overdue (D-025) | badge late; overdue minutes frozen at pause (30 at pause → still 30 after 2 working days paused) |

## Integration (`tests/integration/`)
| ID | Case | Expected |
|---|---|---|
| I-1 | Two agents claim same ticket concurrently (threads) | exactly one 200, one 409 `already_claimed` |
| I-2 | Non-assignee replies | 403 |
| I-3 | Reply with stale expected_version after customer message | 409 `stale_version` |
| I-4 | Canary: note body `CANARY-<uuid>`; call every customer + public endpoint, transcript.csv, late report csv, agent list previews | canary absent everywhere |
| I-5 | `UPDATE audit_events …` / `DELETE` / `TRUNCATE` as app role | error |
| I-6 | Same for messages and internal_notes | error |
| I-7 | Tamper a row as owner, call verify | ok=false, first_bad_id = that row |
| I-8 | Every illegal transition from the state machine table | 409 `illegal_transition` |
| I-9 | Customer reply to waiting ticket resumes clock | status open, due recalculated |
| I-10 | Customer writes to closed ticket | new ticket with parent_ticket_id |
| I-11 | Sweep closes silent waiting ticket after 5 working days; actor system | closed, audit event |
| I-12 | Login lockout after 5 failures; audited | 423 / locked, events present |
| I-13 | Non-GET agent request without `X-Requested-With` | 403 |
| I-14 | Customer token for ticket A cannot read ticket B | 404 |

## Architecture (`tests/architecture/`)
| ID | Case |
|---|---|
| A-1 | `app/schemas/customer.py`, `app/api/customer.py`, `app/api/public.py` do not import `InternalNote` or reference `internal_notes` |
| A-2 | Nothing in `app/sla/` imports fastapi, sqlalchemy, or calls `datetime.now` |

## Sprint gate (must pass before the next sprint)
1. `uv run ruff check .` clean
2. `uv run pytest` green
3. `uv run pip-audit` reviewed
4. SECURITY.md checklist ticked
5. TIMELOG.md updated, DECISIONS.md updated if anything changed
