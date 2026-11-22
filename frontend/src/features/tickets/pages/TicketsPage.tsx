/** UI-1 list screen: Mine / Unassigned / Late / Waiting / All (D-034), polling every 30 s. */
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import type { View } from '../../../api/types'
import { Button } from '../../../components/ui/Button'
import { EmptyState, PageSkeleton } from '../../../components/ui/Card'
import { ErrorState } from '../../../components/ui/ErrorState'
import { Tabs } from '../../../components/ui/Tabs'
import { VIEWS } from '../../../lib/labels'
import { usePageTitle } from '../../../lib/usePageTitle'
import { NewTicketDialog } from '../components/NewTicketDialog'
import { TicketCards, TicketTable } from '../components/TicketList'
import { useTickets } from '../queries'

const EMPTY_TEXT: Record<View, string> = {
  mine: 'Nothing assigned to you. Take a ticket from Unassigned.',
  unassigned: 'Every ticket has an owner.',
  late: 'No late tickets. Nice.',
  waiting: 'No ticket is waiting on a customer.',
  all: 'No tickets yet.',
}

function isView(value: string | null): value is View {
  return VIEWS.some((v) => v.id === value)
}

export default function TicketsPage() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('view')
  const view: View = isView(raw) ? raw : 'mine'
  const tickets = useTickets(view)
  usePageTitle(`Tickets · ${VIEWS.find((v) => v.id === view)?.label ?? ''}`)
  const [creating, setCreating] = useState(false)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Tickets</h1>
          <p className="text-sm text-slate-600">
            Active first — late, then nearest due. Updates every 30 seconds.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>New ticket</Button>
      </div>

      <Tabs label="Ticket views" items={VIEWS} value={view}
        onChange={(next) => setParams({ view: next }, { replace: true })} />

      <div role="tabpanel" aria-label={VIEWS.find((v) => v.id === view)?.label}>
        {tickets.isPending && <PageSkeleton />}
        {tickets.isError && <ErrorState error={tickets.error} onRetry={() => void tickets.refetch()} />}
        {tickets.isSuccess && tickets.data.length === 0 && <EmptyState title={EMPTY_TEXT[view]} />}
        {tickets.isSuccess && tickets.data.length > 0 && (
          <>
            <TicketTable rows={tickets.data} />
            <TicketCards rows={tickets.data} />
            {tickets.data.length >= 200 && (
              <p className="mt-3 text-sm text-slate-600">Showing the first 200 tickets.</p>
            )}
          </>
        )}
      </div>

      <NewTicketDialog open={creating} onClose={() => setCreating(false)} />
    </div>
  )
}
