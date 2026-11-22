/** SLA-3 / D-014 holidays (lead). Working hours themselves are fixed. */
import { useState } from 'react'
import type { FormEvent } from 'react'
import type { Holiday } from '../../../api/types'
import { Button } from '../../../components/ui/Button'
import { Card, EmptyState, PageSkeleton } from '../../../components/ui/Card'
import { Dialog } from '../../../components/ui/Dialog'
import { ErrorState, InlineError } from '../../../components/ui/ErrorState'
import { TextField } from '../../../components/ui/Field'
import { formatCalendarDate } from '../../../lib/format'
import { useAddHoliday, useHolidays, useRemoveHoliday } from '../queries'

export default function HolidaysPage() {
  const holidays = useHolidays()
  const add = useAddHoliday()
  const remove = useRemoveHoliday()
  const [date, setDate] = useState('')
  const [name, setName] = useState('')
  const [removing, setRemoving] = useState<Holiday | null>(null)

  function onAdd(event: FormEvent) {
    event.preventDefault()
    add.mutate({ date, name: name.trim() }, {
      onSuccess: () => { setDate(''); setName('') },
    })
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">Holidays</h1>
        <p className="text-sm text-slate-600">Non-working days for every SLA clock.</p>
      </div>

      <div className="rounded-2xl bg-brand-50 p-4 ring-1 ring-brand-200 sm:p-5">
        <p className="font-semibold text-navy-900">Working hours are fixed</p>
        <p className="mt-1 text-sm">
          Monday–Friday, 09:30–18:30 IST. SLA clocks run only in these hours and stop on the
          holidays below. Adding or removing a holiday moves the due times of open tickets.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
        <Card>
          <h2 className="font-semibold">Holiday list</h2>
          <div className="mt-3">
            {holidays.isPending && <PageSkeleton rows={3} />}
            {holidays.isError && <ErrorState error={holidays.error}
              onRetry={() => void holidays.refetch()} />}
            {holidays.isSuccess && holidays.data.length === 0 && <EmptyState title="No holidays." />}
            {holidays.isSuccess && holidays.data.length > 0 && (
              <ul className="divide-y divide-slate-100">
                {holidays.data.map((h) => (
                  <li key={h.date} className="flex items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <p className="font-semibold text-navy-900">{h.name}</p>
                      <p className="text-sm text-slate-600">{formatCalendarDate(h.date)}</p>
                    </div>
                    <Button variant="ghost" onClick={() => setRemoving(h)}
                      aria-label={`Remove ${h.name}, ${formatCalendarDate(h.date)}`}>
                      Remove
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>

        <Card>
          <h2 className="font-semibold">Add a holiday</h2>
          <form className="mt-3 space-y-4" onSubmit={onAdd}>
            <TextField label="Date" type="date" required value={date}
              onChange={(e) => setDate(e.target.value)} />
            <TextField label="Name" required maxLength={200} value={name}
              placeholder="e.g. Diwali" onChange={(e) => setName(e.target.value)} />
            <InlineError error={add.error} />
            <Button type="submit" className="w-full" busy={add.isPending}
              disabled={!date || !name.trim()}>
              Add holiday
            </Button>
          </form>
        </Card>
      </div>

      <Dialog open={removing !== null} size="sm" title="Remove holiday?"
        onClose={() => setRemoving(null)}
        actions={<>
          <Button variant="secondary" onClick={() => setRemoving(null)}>Cancel</Button>
          <Button variant="danger" busy={remove.isPending} onClick={() => removing &&
            remove.mutate(removing.date, { onSettled: () => setRemoving(null) })}>
            Remove
          </Button>
        </>}>
        {removing && (
          <p>
            <strong>{removing.name}</strong> ({formatCalendarDate(removing.date)}) becomes a
            working day again. Due times of open tickets will move earlier.
          </p>
        )}
      </Dialog>
    </div>
  )
}
