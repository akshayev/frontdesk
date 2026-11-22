/** Human labels for statuses, priorities and audit events (agent side), and the customer status
 * labels (D-033). */
import type { AuditEvent, CustomerTicket, Priority, TicketStatus, View } from '../api/types'
import { formatIST } from './format'

export const STATUS_LABEL: Record<TicketStatus, string> = {
  new: 'New',
  open: 'Open',
  waiting_on_customer: 'Waiting on customer',
  resolved: 'Resolved',
  closed: 'Closed',
}

export const STATUS_TONE: Record<TicketStatus, string> = {
  new: 'bg-brand-100 text-brand-800',
  open: 'bg-sky-100 text-sky-900',
  waiting_on_customer: 'bg-slate-200 text-slate-800',
  resolved: 'bg-emerald-100 text-emerald-900',
  closed: 'bg-slate-100 text-slate-600',
}

export const PRIORITY_LABEL: Record<Priority, string> = {
  urgent: 'Urgent',
  medium: 'Medium',
  low: 'Low',
}

export const PRIORITY_TONE: Record<Priority, string> = {
  urgent: 'text-red-800 bg-red-50 ring-red-200',
  medium: 'text-amber-900 bg-amber-50 ring-amber-200',
  low: 'text-slate-700 bg-white ring-slate-200',
}

export const PRIORITIES: readonly Priority[] = ['urgent', 'medium', 'low']

export const VIEWS: readonly { id: View; label: string }[] = [
  { id: 'mine', label: 'Mine' },
  { id: 'unassigned', label: 'Unassigned' },
  { id: 'late', label: 'Late' },
  { id: 'waiting', label: 'Waiting' },
  { id: 'all', label: 'All' },
]

/** Customer-facing status label (D-033). */
export function customerStatusLabel(ticket: Pick<CustomerTicket, 'status' | 'can_reopen' |
  'reopen_until'>): string {
  switch (ticket.status) {
    case 'new':
      return 'Received — we will reply soon'
    case 'open':
      return 'We are working on it'
    case 'waiting_on_customer':
      return 'Waiting for your reply'
    case 'resolved':
      if (ticket.can_reopen && ticket.reopen_until) {
        return `Resolved — not fixed? You can reopen until ${formatIST(ticket.reopen_until)}`
      }
      return 'Closed — writing here starts a new request'
    case 'closed':
      return 'Closed — writing here starts a new request'
  }
}

const CLOSE_REASON: Record<string, string> = {
  no_customer_reply: 'no reply from the customer for 5 working days',
  reopen_window_expired: 'the 7-day reopen window ended',
}

function str(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function statusWord(value: unknown): string {
  const s = str(value)
  return s && s in STATUS_LABEL ? STATUS_LABEL[s as TicketStatus] : (s ?? '?')
}

function priorityWord(value: unknown): string {
  const s = str(value)
  return s && s in PRIORITY_LABEL ? PRIORITY_LABEL[s as Priority] : (s ?? '?')
}

/** One timeline line (AUD-4). Payloads carry ids only (LEAK-3), so no message text here. */
export function eventLabel(event: Pick<AuditEvent, 'event_type' | 'payload'>): string {
  const p = event.payload
  switch (event.event_type) {
    case 'ticket_created':
      return 'created the ticket'
    case 'claimed':
      return 'took the ticket'
    case 'released':
      return 'released the ticket'
    case 'assigned':
      return 'assigned the ticket'
    case 'customer_message':
      return 'wrote a message'
    case 'agent_reply':
      return p.wait_for_customer === true
        ? 'replied and is waiting for the customer'
        : 'replied to the customer'
    case 'note_added':
      return 'added an internal note'
    case 'status_changed':
      return `changed status: ${statusWord(p.from)} → ${statusWord(p.to)}`
    case 'priority_changed':
      return `changed priority: ${priorityWord(p.from)} → ${priorityWord(p.to)}`
    case 'resolved':
      return 'resolved the ticket'
    case 'reopened':
      return 'reopened the ticket'
    case 'auto_closed': {
      const reason = str(p.reason)
      return `closed the ticket (${reason ? (CLOSE_REASON[reason] ?? reason) : 'rule'})`
    }
    default:
      return event.event_type.replaceAll('_', ' ')
  }
}
