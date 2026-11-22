/** RPT-1 / RPT-2 late report and AUD-3 audit verification (lead only). */
import { Link } from 'react-router'
import type { LateRow, VerifyResult } from '../../../api/types'
import { PriorityBadge, StatusPill } from '../../../components/ui/Badge'
import { Button } from '../../../components/ui/Button'
import { buttonClass } from '../../../components/ui/buttonClass'
import { Card, EmptyState, PageSkeleton } from '../../../components/ui/Card'
import { ErrorState } from '../../../components/ui/ErrorState'
import { CheckIcon, AlertIcon, DownloadIcon, ShieldIcon } from '../../../components/ui/Icon'
import { targetLabel } from '../../../lib/badge'
import { formatCount, formatIST, formatWorkingMinutes, ticketNumber } from '../../../lib/format'
import { PRIORITY_LABEL } from '../../../lib/labels'
import { LATE_CSV_URL, useAuditVerify, useLateReport } from '../queries'

function Missed({ row }: { row: LateRow }) {
  return (
    <ul className="space-y-1">
      {row.missed.map((m) => (
        <li key={m.target}>
          <span className="font-semibold text-red-800">{targetLabel(m.target)}</span>{' '}
          late by {formatWorkingMinutes(m.working_minutes_late)}
          <span className="block text-xs text-slate-600">
            due {formatIST(m.due_at)}{m.met_at ? ` · met ${formatIST(m.met_at)}` : ' · not met yet'}
          </span>
        </li>
      ))}
    </ul>
  )
}

function History({ row }: { row: LateRow }) {
  if (row.priority_history.length === 0) {
    return <span>{PRIORITY_LABEL[row.initial_priority]} (unchanged)</span>
  }
  return (
    <ol className="space-y-1">
      <li>Started {PRIORITY_LABEL[row.initial_priority]}</li>
      {row.priority_history.map((c) => (
        <li key={c.at}>
          {PRIORITY_LABEL[c.from_priority]} → {PRIORITY_LABEL[c.to_priority]}
          <span className="block text-xs text-slate-600">{formatIST(c.at)}</span>
        </li>
      ))}
    </ol>
  )
}

function waiting(row: LateRow): string {
  return row.waiting_on_customer_working_minutes > 0
    ? formatWorkingMinutes(row.waiting_on_customer_working_minutes) : '—'
}

function VerifyPanel() {
  const verify = useAuditVerify()
  const result: VerifyResult | undefined = verify.data
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <ShieldIcon className="mt-0.5 size-6 text-brand-600" />
          <div>
            <h2 className="font-semibold">Audit log integrity</h2>
            <p className="text-sm">Recomputes the sha256 hash chain over every event.</p>
          </div>
        </div>
        <Button variant="secondary" busy={verify.isFetching} onClick={() => void verify.refetch()}>
          Verify audit log
        </Button>
      </div>
      <div aria-live="polite">
        {result && !verify.isFetching && (result.ok ? (
          <p className="mt-4 flex items-center gap-2 rounded-xl bg-emerald-50 p-3 font-semibold
            text-emerald-900 ring-1 ring-emerald-300">
            <CheckIcon className="size-5" />
            Intact — {formatCount(result.checked)} events checked
          </p>
        ) : (
          <p className="mt-4 flex items-center gap-2 rounded-xl bg-red-50 p-3 font-semibold
            text-red-900 ring-1 ring-red-300">
            <AlertIcon className="size-5" />
            Broken at event #{result.first_bad_id ?? '?'} — {formatCount(result.checked)} events
            checked. The history from that event on cannot be trusted.
          </p>
        ))}
      </div>
      {verify.isError && <div className="mt-4"><ErrorState error={verify.error} /></div>}
    </Card>
  )
}

export default function LateReportPage() {
  const report = useLateReport()
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Late tickets</h1>
          <p className="text-sm text-slate-600">
            Every ticket that missed a target, by how many working minutes, and why.
          </p>
        </div>
        <a href={LATE_CSV_URL} download className={buttonClass('secondary')}>
          <DownloadIcon className="size-4" /> Download CSV
        </a>
      </div>

      <VerifyPanel />

      {report.isPending && <PageSkeleton />}
      {report.isError && <ErrorState error={report.error} onRetry={() => void report.refetch()} />}
      {report.isSuccess && report.data.length === 0 && <EmptyState title="No late tickets." />}
      {report.isSuccess && report.data.length > 0 && (
        <>
          <div className="hidden overflow-x-auto rounded-2xl bg-white shadow-sm ring-1
            ring-slate-200 md:block">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Late tickets</caption>
              <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide
                text-slate-600">
                <tr>
                  <th scope="col" className="px-4 py-3">Ticket</th>
                  <th scope="col" className="px-4 py-3">Assignee</th>
                  <th scope="col" className="px-4 py-3">Missed</th>
                  <th scope="col" className="px-4 py-3">Priority history</th>
                  <th scope="col" className="px-4 py-3">Waiting on customer</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 align-top">
                {report.data.map((row) => (
                  <tr key={row.ticket_id}>
                    <td className="px-4 py-3">
                      <Link to={`/tickets/${row.ticket_id}`} className="font-semibold
                        text-navy-900 hover:text-brand-700 hover:underline">
                        <span className="font-mono text-xs text-slate-600">
                          {ticketNumber(row.number)}
                        </span>{' '}{row.subject}
                      </Link>
                      <div className="mt-1 flex gap-2">
                        <StatusPill status={row.status} />
                        <PriorityBadge priority={row.current_priority} />
                      </div>
                    </td>
                    <td className="px-4 py-3">{row.assignee?.name ?? 'Unassigned'}</td>
                    <td className="px-4 py-3"><Missed row={row} /></td>
                    <td className="px-4 py-3"><History row={row} /></td>
                    <td className="px-4 py-3">{waiting(row)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="space-y-3 md:hidden">
            {report.data.map((row) => (
              <li key={row.ticket_id} className="rounded-2xl bg-white p-4 text-sm shadow-sm ring-1
                ring-slate-200">
                <Link to={`/tickets/${row.ticket_id}`} className="font-semibold text-navy-900">
                  <span className="font-mono text-xs text-slate-600">{ticketNumber(row.number)}</span>
                  {' '}{row.subject}
                </Link>
                <div className="mt-2 flex flex-wrap gap-2">
                  <StatusPill status={row.status} />
                  <PriorityBadge priority={row.current_priority} />
                </div>
                <dl className="mt-3 space-y-2">
                  <div><dt className="text-xs text-slate-600">Assignee</dt>
                    <dd>{row.assignee?.name ?? 'Unassigned'}</dd></div>
                  <div><dt className="text-xs text-slate-600">Missed</dt><dd><Missed row={row} /></dd></div>
                  <div><dt className="text-xs text-slate-600">Priority history</dt>
                    <dd><History row={row} /></dd></div>
                  <div><dt className="text-xs text-slate-600">Waiting on customer</dt>
                    <dd>{waiting(row)}</dd></div>
                </dl>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
