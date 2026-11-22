/** UI-2 list: a table on desktop (md+), cards on phones. Preview is public-only (UI-3). */
import { Link } from 'react-router'
import type { TicketRow } from '../../../api/types'
import { PriorityBadge, SlaBadge, StatusPill } from '../../../components/ui/Badge'
import { formatIST, ticketNumber } from '../../../lib/format'

function Assignee({ row }: { row: TicketRow }) {
  return row.assignee
    ? <span>{row.assignee.name}</span>
    : <span className="italic text-slate-500">Unassigned</span>
}

export function TicketTable({ rows }: { rows: TicketRow[] }) {
  return (
    <div className="hidden overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200
      md:block">
      <table className="w-full table-fixed text-left text-sm">
        <caption className="sr-only">Tickets, nearest due first</caption>
        <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th scope="col" className="w-24 px-4 py-3">Ticket</th>
            <th scope="col" className="px-4 py-3">Subject</th>
            <th scope="col" className="hidden w-36 px-4 py-3 lg:table-cell">Customer</th>
            <th scope="col" className="w-24 px-4 py-3">Priority</th>
            <th scope="col" className="w-40 px-4 py-3">Status</th>
            <th scope="col" className="hidden w-32 px-4 py-3 xl:table-cell">Assignee</th>
            <th scope="col" className="w-36 px-4 py-3">SLA</th>
            <th scope="col" className="hidden w-40 px-4 py-3 xl:table-cell">Last activity</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={row.id} className="group relative align-top hover:bg-brand-50/50">
              <td className="px-4 py-3 font-mono text-xs font-semibold text-slate-600">
                {ticketNumber(row.number)}
              </td>
              <td className="px-4 py-3">
                {/* The stretched link makes the whole row clickable while staying one link. */}
                <Link to={`/tickets/${row.id}`} className="font-semibold text-navy-900
                  after:absolute after:inset-0 group-hover:text-brand-700">
                  {row.subject}
                </Link>
                {row.preview && <p className="mt-0.5 truncate text-slate-600">{row.preview}</p>}
                <p className="mt-0.5 text-xs text-slate-500 lg:hidden">{row.customer_name}</p>
              </td>
              <td className="hidden truncate px-4 py-3 lg:table-cell">{row.customer_name}</td>
              <td className="px-4 py-3"><PriorityBadge priority={row.priority} /></td>
              <td className="px-4 py-3">
                <StatusPill status={row.status} />
                <p className="mt-1 text-xs xl:hidden"><Assignee row={row} /></p>
              </td>
              <td className="hidden truncate px-4 py-3 xl:table-cell"><Assignee row={row} /></td>
              <td className="px-4 py-3"><SlaBadge badge={row.badge} dueAt={row.due_at} /></td>
              <td className="hidden px-4 py-3 text-slate-600 xl:table-cell">
                {formatIST(row.last_activity_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function TicketCards({ rows }: { rows: TicketRow[] }) {
  return (
    <ul className="space-y-3 md:hidden">
      {rows.map((row) => (
        <li key={row.id} className="relative rounded-2xl bg-white p-4 shadow-sm ring-1
          ring-slate-200">
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-xs font-semibold text-slate-600">
              {ticketNumber(row.number)}
            </span>
            <SlaBadge badge={row.badge} dueAt={row.due_at} />
          </div>
          <Link to={`/tickets/${row.id}`} className="mt-2 block font-semibold text-navy-900
            after:absolute after:inset-0">
            {row.subject}
          </Link>
          {row.preview && <p className="mt-1 line-clamp-2 text-sm text-slate-600">{row.preview}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <PriorityBadge priority={row.priority} />
            <StatusPill status={row.status} />
            <span className="text-slate-600">{row.customer_name} · <Assignee row={row} /></span>
          </div>
          <p className="mt-2 text-xs text-slate-500">Last activity {formatIST(row.last_activity_at)}</p>
        </li>
      ))}
    </ul>
  )
}
