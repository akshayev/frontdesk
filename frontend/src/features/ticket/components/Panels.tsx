/** Ticket page side panels: SLA (both targets, D-025), details, audit timeline (AUD-4).
 * On phones the SLA panel and the timeline collapse. */
import { useId, useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import type { AuditEvent, Badge as BadgeData, TargetStatus, Ticket } from '../../../api/types'
import { PriorityBadge, SlaBadge, StatusPill } from '../../../components/ui/Badge'
import { ChevronIcon } from '../../../components/ui/Icon'
import { targetLabel } from '../../../lib/badge'
import { formatIST, formatISTExact } from '../../../lib/format'
import { eventLabel } from '../../../lib/labels'

/** Always open on desktop; a disclosure button on phones. */
export function Collapsible({ title, summary, children, defaultOpen = false }: {
  title: string; summary?: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const id = useId()
  return (
    <section className="rounded-2xl bg-white shadow-sm ring-1 ring-slate-200"
      aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className="text-base font-semibold">
        <button type="button" aria-expanded={open} aria-controls={id}
          onClick={() => setOpen((o) => !o)}
          className="flex min-h-12 w-full items-center gap-3 px-4 py-3 text-left lg:hidden">
          <span className="flex-1">{title}</span>
          {summary}
          <ChevronIcon className={`size-5 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        <span className="hidden px-5 pt-4 lg:block">{title}</span>
      </h2>
      <div id={id} className={`${open ? 'block' : 'hidden'} px-4 pb-4 lg:block lg:px-5 lg:pb-5
        lg:pt-3`}>
        {children}
      </div>
    </section>
  )
}

export function SlaPanel({ targets, badge }: { targets: TargetStatus[]; badge: BadgeData }) {
  const shown = targets.find((t) => t.target === badge.target)
  return (
    <Collapsible title="SLA" summary={<SlaBadge badge={badge} dueAt={shown?.due_at ?? null} />}>
      <dl className="space-y-3">
        {targets.map((t) => (
          <div key={t.target} className="rounded-xl bg-slate-50 p-3">
            <div className="flex items-center justify-between gap-2">
              <dt className="font-semibold text-navy-900">{targetLabel(t.target)}</dt>
              <dd><SlaBadge badge={t} dueAt={t.due_at} /></dd>
            </div>
            <dd className="mt-1 text-sm">
              {t.met_at ? <>Met {formatIST(t.met_at)} · was due {formatIST(t.due_at)}</>
                : <>Due {formatIST(t.due_at)}</>}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs text-slate-600">
        Working time only: 09:30–18:30 IST, Monday–Friday, excluding holidays.
      </p>
    </Collapsible>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-2">
      <dt className="text-sm text-slate-600">{label}</dt>
      <dd className="min-w-0 text-right text-sm font-medium text-navy-900">{children}</dd>
    </div>
  )
}

export function DetailsPanel({ ticket }: { ticket: Ticket }) {
  return (
    <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 lg:p-5"
      aria-labelledby="details-h">
      <h2 id="details-h" className="text-base font-semibold">Details</h2>
      <dl className="mt-2 divide-y divide-slate-100">
        <Row label="Customer">
          <span className="block">{ticket.customer.name}</span>
          <span className="block break-all text-xs font-normal">{ticket.customer.email}</span>
        </Row>
        <Row label="Status"><StatusPill status={ticket.status} /></Row>
        <Row label="Priority"><PriorityBadge priority={ticket.priority} /></Row>
        <Row label="Assignee">{ticket.assignee?.name ?? <span className="italic">Unassigned</span>}</Row>
        <Row label="Created">{formatIST(ticket.created_at)}</Row>
        {ticket.resolved_at && <Row label="Resolved">{formatIST(ticket.resolved_at)}</Row>}
        {ticket.closed_at && <Row label="Closed">{formatIST(ticket.closed_at)}</Row>}
        {ticket.reopen_count > 0 && <Row label="Reopened">{ticket.reopen_count}×</Row>}
        {ticket.parent_ticket_id && (
          <Row label="Follow-up of">
            <Link to={`/tickets/${ticket.parent_ticket_id}`} className="text-brand-700 underline">
              earlier ticket
            </Link>
          </Row>
        )}
      </dl>
    </section>
  )
}

export function Timeline({ events }: { events: AuditEvent[] }) {
  return (
    <Collapsible title="History" summary={<span className="text-sm text-slate-600">
      {events.length} events</span>}>
      <ol className="relative space-y-3 border-l-2 border-slate-200 pl-4">
        {events.map((e) => (
          <li key={e.id} className="relative">
            <span aria-hidden="true" className="absolute -left-[23px] top-1.5 size-3 rounded-full
              border-2 border-white bg-brand-600" />
            <p className="text-sm">
              <span className="font-semibold text-navy-900">{e.actor_name}</span>{' '}
              {eventLabel(e)}
            </p>
            <time dateTime={e.created_at} className="text-xs text-slate-600">
              {formatISTExact(e.created_at)}
            </time>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs text-slate-600">
        From the tamper-evident audit log (timestamps are the database clock).
      </p>
    </Collapsible>
  )
}
