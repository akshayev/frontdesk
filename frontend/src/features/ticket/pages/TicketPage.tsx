/** UI-4 ticket page. Desktop: conversation + composer left, SLA / details / actions / history
 * right. Phone: one column, collapsible SLA and history, composer sticky at the bottom so it
 * stays visible with the on-screen keyboard (D-030). The customer link is never shown here. */
import { Link, useParams } from 'react-router'
import type { Action } from '../../../api/types'
import { PriorityBadge, SlaBadge, StatusPill } from '../../../components/ui/Badge'
import { PageSkeleton } from '../../../components/ui/Card'
import { ErrorState } from '../../../components/ui/ErrorState'
import { ticketNumber } from '../../../lib/format'
import { ActionsPanel } from '../components/Actions'
import { Composer } from '../components/Composer'
import { Conversation } from '../components/Conversation'
import { DetailsPanel, SlaPanel, Timeline } from '../components/Panels'
import { useTicket } from '../queries'

export default function TicketPage() {
  const { id = '' } = useParams()
  const query = useTicket(id)

  if (query.isPending) return <PageSkeleton rows={6} />
  if (query.isError) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()}>
      <Link to="/tickets" className="mt-3 block text-sm font-semibold underline">Back to tickets</Link>
    </ErrorState>
  }

  const detail = query.data
  const { ticket } = detail
  const allowed = new Set(detail.allowed_actions as Action[])
  const shownTarget = detail.targets.find((t) => t.target === detail.badge.target)

  return (
    <div className="space-y-4">
      <div>
        <Link to="/tickets" className="text-sm font-semibold text-brand-700 hover:underline">
          ← Tickets
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-semibold text-slate-600">
            {ticketNumber(ticket.number)}
          </span>
          <StatusPill status={ticket.status} />
          <PriorityBadge priority={ticket.priority} />
          <SlaBadge badge={detail.badge} dueAt={shownTarget?.due_at ?? null} />
        </div>
        <h1 className="mt-1 break-words text-xl font-semibold sm:text-2xl">{ticket.subject}</h1>
        <p className="text-sm text-slate-600">
          {ticket.customer.name} · {ticket.assignee ? `Owner: ${ticket.assignee.name}` : 'Unassigned'}
        </p>
      </div>

      {/* Phone order: SLA → actions → conversation + composer → details → history.
          Desktop: conversation spans the left column; the panels stack on the right. */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]
        lg:grid-rows-[auto_auto_auto_auto_1fr] lg:items-start">
        <div className="lg:col-start-2">
          <SlaPanel targets={detail.targets} badge={detail.badge} />
        </div>
        <div className="lg:col-start-2">
          <ActionsPanel detail={detail} />
        </div>
        <div className="space-y-4 lg:col-start-1 lg:row-span-5 lg:row-start-1">
          <section aria-label="Conversation and internal notes"
            className="rounded-2xl bg-slate-100/70 p-3 sm:p-4">
            <Conversation messages={detail.messages} notes={detail.notes}
              customerName={ticket.customer.name} />
          </section>
          {allowed.has('note') && (
            <div className="sticky bottom-0 z-20 -mx-4 bg-linear-to-t from-slate-50 via-slate-50
              to-transparent px-4 pb-3 pt-4 sm:mx-0 sm:px-0 lg:static lg:bg-none lg:p-0">
              <Composer ticketId={ticket.id} version={detail.version}
                customerName={ticket.customer.name} canReply={allowed.has('reply')}
                canWait={allowed.has('reply_and_wait')} />
            </div>
          )}
        </div>
        <div className="lg:col-start-2">
          <DetailsPanel ticket={ticket} />
        </div>
        <div className="lg:col-start-2">
          <Timeline events={detail.events} />
        </div>
      </div>
    </div>
  )
}
