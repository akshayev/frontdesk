# Frontdesk — Product Requirements (derived from the iNav hiring test story)

Source: "Hiring Test – Full Stack Developer" (iNav Technologies, 21-11-2026), Sections 2–4.
Every rule below cites where in the story it came from. Rules marked **[DECISION]** are our interpretation of something the story leaves unclear; see docs/DECISIONS.md.

## 1. Users
| Actor | Description |
|---|---|
| Agent | One of 9 support agents. Logs in. Claims, replies, writes internal notes, changes status/priority. |
| Lead | Support lead (Meera). Everything an agent can do + late report, holidays, reassign, audit verify. |
| Customer | No account. Reaches one ticket through a secret link. Can view public messages, reply, reopen. |
| System | Background sweep (auto-close). Recorded as actor `system` in the audit log. |

## 2. SLA rules (Section 3, paragraph 1–2)
| ID | Rule |
|---|---|
| SLA-1 | Priorities: `urgent` (customer cannot work at all), `medium`, `low` (questions, small requests). |
| SLA-2 | Targets in **working minutes**: urgent 120 response / 540 resolution [DECISION D-009]; medium 270 / 1620; low 540 / 2700. |
| SLA-3 | Working time = 09:30–18:30 Asia/Kolkata, Monday–Friday, excluding dates in the `holidays` table. |
| SLA-4 | Acceptance: urgent ticket created Fri 18:00 IST → first response due **Mon 11:00 IST** (30 min Fri + 90 min Mon). It must not show as late on Sat/Sun. |
| SLA-5 | First response is met by the first **public agent reply**. Internal notes never count. |
| SLA-6 | Resolution is met when the ticket moves to `resolved`. Resolve requires a met first response (at least one public agent reply), else 409 `reply_required` [D-027]. |
| SLA-7 | A ticket is **late** if a target was met after its due time, or is unmet and now > due time. |
| SLA-8 | **At risk** = unmet and less than 25% of the target's working minutes remain. |

## 3. Waiting on customer (Section 3, paragraph 3–4)
| ID | Rule |
|---|---|
| WAIT-1 | Status `waiting_on_customer` pauses the resolution clock. |
| WAIT-2 | It can only be entered together with a public agent reply (the question being asked). |
| WAIT-3 | On pause store remaining working minutes; on customer reply: status → `open`, resolution due = old due + working minutes spent waiting [D-026] (equals now + remaining for an on-time ticket). If already overdue at pause, the breach is preserved: the ticket stays late by the amount it was late at the pause. |
| WAIT-4 | If the customer does not reply for **5 working days** [D-010], the system closes the ticket (`closed`, reason `no_customer_reply`). |

## 4. Resolve, reopen, close (Section 3, paragraph 5)
| ID | Rule |
|---|---|
| RO-1 | Customer may reopen a `resolved` ticket within **7 calendar days** of `resolved_at` [D-011]. Status → `open`. Resolution clock resumes with the remaining working minutes at resolve time [D-013]: due = old due + working minutes spent resolved [D-026]. |
| RO-2 | A customer reply to a resolved ticket inside the window also reopens it. |
| RO-3 | After 7 calendar days the system closes it (`closed`, reason `reopen_window_expired`). |
| RO-4 | Customer writes to a closed ticket → a **new ticket** is created with `parent_ticket_id` = old ticket [D-012]. |

## 5. Priority change (Section 3, last paragraph — the open question) [D-008]
| ID | Rule |
|---|---|
| PRI-1 | Upgrade: new due = min(old due, change time + new target). |
| PRI-2 | Downgrade: new due = created_at + new target in working minutes, excluding paused time. |
| PRI-3 | An already-met target stays met and is not recalculated. |
| PRI-4 | While paused, the same rules apply to the stored remaining minutes: upgrade → remaining = min(remaining, new target); downgrade → remaining = new target − (old target − remaining). |
| PRI-5 | Every change writes a `priority_changed` audit event with old/new priority and old/new due times. |

## 6. Agent screen (Section 3, paragraph 6)
| ID | Rule |
|---|---|
| UI-1 | One list screen with views: Mine, Unassigned, All, Late, Waiting on customer. |
| UI-2 | Each row shows: number, subject, customer, priority, status, assignee, SLA badge (late / at risk / paused / on track) with working time left or overdue. Default sort: nearest due first. |
| UI-3 | Row preview text comes from **public messages only**. |
| UI-4 | Ticket page: public conversation, internal notes (visually distinct, yellow), audit timeline, SLA panel. |
| UI-5 | Two separate composers: "Reply to customer" and "Internal note". Reply has an option "and wait for customer". |
| UI-6 | "Take this ticket" button; status and priority controls. |
| UI-7 | List refreshes automatically (polling every 30 s). |

## 7. INC-0291 — double claim (Section 4.1)
| ID | Rule |
|---|---|
| CLM-1 | Claiming is atomic: only one agent can succeed; the other gets HTTP 409 with the current owner's name. |
| CLM-2 | Only the assignee can send a public reply, resolve or set waiting (lead may reassign). |
| CLM-3 | Every mutating request carries `expected_version`. If the ticket changed since the agent loaded it (e.g. new customer message), the server returns 409 "ticket changed, review before sending". |

## 8. INC-0304 — internal notes leak (Section 4.2)
| ID | Rule |
|---|---|
| LEAK-1 | Internal notes are never returned by any customer endpoint, never in an export, never in a list preview, never in search, never in a customer-visible event. |
| LEAK-2 | Notes are stored in their own table `internal_notes`; customer code paths never import or query it. |
| LEAK-3 | Audit event payloads reference notes by id only, never by body. |

## 9. INC-0318 — provable history (Section 4.3)
| ID | Rule |
|---|---|
| AUD-1 | Every state change writes an audit event in the same DB transaction: what, when (DB clock), who (agent/customer/system). |
| AUD-2 | Audit events, messages and notes cannot be updated or deleted (DB-enforced). |
| AUD-3 | Events form a sha256 hash chain; lead can run `/api/lead/audit/verify`. |
| AUD-4 | Ticket page shows the timeline; customer-facing message timestamps are exact (to the second, IST). |

## 10. Management question (Section 2)
| ID | Rule |
|---|---|
| RPT-1 | Lead report "Late tickets": ticket, priority history, which target was missed (response/resolution), by how many working minutes, total time waiting on customer, assignee. |
| RPT-2 | CSV export of the report (contains no note bodies). |

## 11. Intake
| ID | Rule |
|---|---|
| IN-1 | Public "Submit a problem" page: name, email, subject, description, severity (with plain-language explanations). Returns the secret ticket link once. |
| IN-2 | Agents can create a ticket on behalf of a customer (phone/WhatsApp) and get the customer link to share. |

## 12. Out of scope (list in COMPLETION_NOTE.md)
Email/WhatsApp delivery, attachments, real-time websockets, customer accounts, multi-tenant, i18n, holiday import, SLA pause on internal holidays per agent, browser E2E tests.
