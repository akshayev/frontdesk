/** IN-1 "Submit a problem" (phone-first). Severity in plain language → urgent / medium / low. */
import { useId, useState } from 'react'
import type { FormEvent } from 'react'
import { isApiError } from '../../../api/errors'
import type { Priority, PublicTicketCreated } from '../../../api/types'
import { Button } from '../../../components/ui/Button'
import { buttonClass } from '../../../components/ui/buttonClass'
import { TextArea, TextField } from '../../../components/ui/Field'
import { AlertIcon, CheckIcon } from '../../../components/ui/Icon'
import { SecretLink } from '../../../components/ui/SecretLink'
import { ticketNumber } from '../../../lib/format'
import { CustomerShell } from '../../customer/components/CustomerShell'
import { useSubmitRequest } from '../queries'

const SEVERITY: readonly { value: Priority; title: string; text: string }[] = [
  { value: 'urgent', title: 'I cannot work at all',
    text: 'Nothing works, or my whole team is stopped.' },
  { value: 'medium', title: "I'm partly blocked",
    text: 'Something important is broken, but I can keep working around it.' },
  { value: 'low', title: 'A question or small request',
    text: 'How do I…? A small change, an idea, a question about billing.' },
]

const EMPTY = { name: '', email: '', subject: '', description: '' }

export default function NewRequestPage() {
  const submit = useSubmitRequest()
  const [form, setForm] = useState(EMPTY)
  const [priority, setPriority] = useState<Priority | null>(null)
  const [created, setCreated] = useState<PublicTicketCreated | null>(null)
  const severityId = useId()

  const set = (key: keyof typeof EMPTY) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!priority) return
    submit.mutate({ ...form, priority }, { onSuccess: (data) => {
      setCreated(data)
      window.scrollTo({ top: 0 })
    } })
  }

  if (created) {
    return (
      <CustomerShell>
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 sm:p-6">
          <p className="flex items-center gap-2 text-sm font-semibold text-emerald-800">
            <CheckIcon className="size-5" /> Request received
          </p>
          <h1 className="mt-2 text-2xl font-semibold">
            Your request number is {ticketNumber(created.number)}
          </h1>
          <p className="mt-2">
            We answer during working hours (Monday–Friday, 09:30–18:30 IST). Open the link below
            to follow the conversation and reply.
          </p>
          <div className="mt-5">
            <SecretLink link={created.customer_link} audience="customer" />
          </div>
          <a href={created.customer_link} className={buttonClass('secondary', 'lg', 'mt-5 w-full')}>
            Open my request
          </a>
          <p className="mt-4 text-sm text-slate-600">
            This link is shown only once. We cannot send it again, because we do not store it.
          </p>
        </div>
      </CustomerShell>
    )
  }

  const error = submit.error
  const message = !error ? null
    : isApiError(error) && error.status === 429 ? 'Too many requests — wait a minute and try again.'
      : isApiError(error) ? error.message : 'Could not send your request. Please try again.'

  return (
    <CustomerShell>
      <h1 className="text-2xl font-semibold">Submit a problem</h1>
      <p className="mt-1">Tell us what is wrong. You will get a private link to follow your
        request — no account needed.</p>
      <form className="mt-6 space-y-5 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200
        sm:p-6" onSubmit={onSubmit}>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Your name" required maxLength={200} autoComplete="name"
            value={form.name} onChange={set('name')} />
          <TextField label="Email" type="email" required maxLength={254} autoComplete="email"
            inputMode="email" value={form.email} onChange={set('email')} />
        </div>
        <TextField label="Subject" required maxLength={200} value={form.subject}
          placeholder="e.g. Invoices are not generating" onChange={set('subject')} />

        <fieldset aria-describedby={`${severityId}-hint`}>
          <legend className="text-sm font-semibold text-navy-900">How bad is it?</legend>
          <p id={`${severityId}-hint`} className="text-xs text-slate-600">
            This decides how fast we must answer.
          </p>
          <div className="mt-2 grid gap-2">
            {SEVERITY.map((s) => (
              <label key={s.value} className={`flex min-h-14 cursor-pointer items-start gap-3
                rounded-2xl p-3 ring-1 ring-inset transition-colors has-[:focus-visible]:ring-2
                has-[:focus-visible]:ring-brand-500 ${priority === s.value
                  ? 'bg-brand-50 ring-2 ring-brand-600' : 'bg-white ring-slate-300 hover:bg-slate-50'}`}>
                <input type="radio" name="severity" value={s.value} required
                  checked={priority === s.value} onChange={() => setPriority(s.value)}
                  className="mt-1 size-5 accent-brand-600" />
                <span>
                  <span className="block font-semibold text-navy-900">{s.title}</span>
                  <span className="block text-sm">{s.text}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <TextArea label="What happened?" required rows={6} maxLength={10000}
          value={form.description} onChange={set('description')}
          hint="What were you trying to do, what did you see, since when? Do not include passwords." />

        {message && (
          <p role="alert" className="flex items-start gap-2 rounded-xl bg-red-50 p-3 text-sm
            text-red-900 ring-1 ring-red-200">
            <AlertIcon className="mt-0.5 size-4 shrink-0" />{message}
          </p>
        )}
        <Button type="submit" size="lg" className="w-full" busy={submit.isPending}
          disabled={!priority}>
          Send request
        </Button>
      </form>
    </CustomerShell>
  )
}
