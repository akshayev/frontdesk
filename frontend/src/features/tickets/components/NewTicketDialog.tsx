/** IN-2: an agent records a ticket for a customer who phoned or wrote on WhatsApp. The
 * customer link is shown ONCE with Copy and "Share only with this customer" (D-033). */
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router'
import type { Priority, TicketCreated } from '../../../api/types'
import { Button } from '../../../components/ui/Button'
import { buttonClass } from '../../../components/ui/buttonClass'
import { Dialog } from '../../../components/ui/Dialog'
import { InlineError } from '../../../components/ui/ErrorState'
import { SelectField, TextArea, TextField } from '../../../components/ui/Field'
import { SecretLink } from '../../../components/ui/SecretLink'
import { ticketNumber } from '../../../lib/format'
import { PRIORITIES, PRIORITY_LABEL } from '../../../lib/labels'
import { useCreateTicket } from '../queries'

const EMPTY = { customer_name: '', customer_email: '', subject: '', body: '',
  priority: 'medium' as Priority }

export function NewTicketDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateTicket()
  const [form, setForm] = useState(EMPTY)
  const [created, setCreated] = useState<TicketCreated | null>(null)

  function close() {
    // The link is gone for good once the dialog closes (only its hash is stored).
    setCreated(null)
    setForm(EMPTY)
    create.reset()
    onClose()
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    create.mutate(form, { onSuccess: (data) => setCreated(data) })
  }

  const set = (key: keyof typeof EMPTY) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  if (created) {
    return (
      <Dialog open={open} onClose={close} title={`${ticketNumber(created.number)} created`}
        actions={<>
          <Link to={`/tickets/${created.id}`} onClick={close} className={buttonClass('secondary')}>
            Open ticket
          </Link>
          <Button onClick={close}>Done</Button>
        </>}>
        <p className="mb-4">Send this link to the customer so they can follow and answer the
          request. It will not be shown again.</p>
        <SecretLink link={created.customer_link} audience="agent" />
      </Dialog>
    )
  }

  return (
    <Dialog open={open} onClose={close} title="New ticket for a customer"
      actions={<>
        <Button variant="secondary" onClick={close}>Cancel</Button>
        <Button type="submit" form="new-ticket-form" busy={create.isPending}>Create ticket</Button>
      </>}>
      <form id="new-ticket-form" className="space-y-4" onSubmit={onSubmit}>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Customer name" required maxLength={200} autoComplete="off"
            value={form.customer_name} onChange={set('customer_name')} />
          <TextField label="Customer email" type="email" required maxLength={254}
            autoComplete="off" value={form.customer_email} onChange={set('customer_email')} />
        </div>
        <TextField label="Subject" required maxLength={200} value={form.subject}
          onChange={set('subject')} />
        <SelectField label="Priority" value={form.priority} onChange={set('priority')}
          hint="Urgent: the customer cannot work at all. Low: a question or small request.">
          {PRIORITIES.map((p) => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
        </SelectField>
        <TextArea label="What the customer reported" required rows={5} maxLength={10000}
          value={form.body} onChange={set('body')}
          hint="Recorded as the customer's first message — the customer will see it." />
        <InlineError error={create.error} />
      </form>
    </Dialog>
  )
}
