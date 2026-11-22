/**
 * The customer's ticket page (phone-first). Token from location.hash, kept there (D-038).
 * Chat thread with exact IST times (AUD-4), sticky reply box (highlighted and focused while we
 * wait for the customer), Reopen only when the server says so (RO-1), and the RO-4 follow-up
 * link shown once. Polls every 30 s.
 */
import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useLocation } from 'react-router'
import { isApiError } from '../../../api/errors'
import type { CustomerTicket, CustomerWrite } from '../../../api/types'
import { Button } from '../../../components/ui/Button'
import { buttonClass } from '../../../components/ui/buttonClass'
import { PageSkeleton } from '../../../components/ui/Card'
import { ErrorState } from '../../../components/ui/ErrorState'
import { AlertIcon, SendIcon } from '../../../components/ui/Icon'
import { CopyButton, SecretLink } from '../../../components/ui/SecretLink'
import { formatISTExact, ticketNumber } from '../../../lib/format'
import { customerStatusLabel } from '../../../lib/labels'
import { usePageTitle } from '../../../lib/usePageTitle'
import { CustomerShell } from '../components/CustomerShell'
import { readToken, useCustomerReply, useCustomerTicket, useReopen } from '../queries'

const STATUS_TONE: Record<CustomerTicket['status'], string> = {
  new: 'bg-brand-100 text-brand-800',
  open: 'bg-sky-100 text-sky-900',
  waiting_on_customer: 'bg-amber-200 text-amber-950',
  resolved: 'bg-emerald-100 text-emerald-900',
  closed: 'bg-slate-200 text-slate-700',
}

function InvalidLink() {
  usePageTitle('This link is not valid', 'Arvo Systems support')
  return (
    <CustomerShell>
      <div className="rounded-2xl bg-white p-6 text-center shadow-sm ring-1 ring-slate-200">
        <h1 className="text-xl font-semibold">This link is not valid</h1>
        <p className="mt-2">
          Check that you opened the full link from your message. If you lost it, please submit
          your problem again — we will give you a new link.
        </p>
        <Link to="/new" className={buttonClass('primary', 'lg', 'mt-5')}>Submit a problem</Link>
      </div>
    </CustomerShell>
  )
}

function Thread({ ticket }: { ticket: CustomerTicket }) {
  return (
    <ol className="space-y-3" aria-label="Conversation">
      {ticket.messages.map((m, i) => {
        const mine = m.author === 'You'
        const who = mine ? 'You' : `Support${m.agent_first_name ? ` · ${m.agent_first_name}` : ''}`
        return (
          <li key={`${m.created_at}-${i}`} className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-3 shadow-sm ${mine
              ? 'rounded-br-md bg-brand-600 text-white'
              : 'rounded-bl-md bg-white text-navy-900 ring-1 ring-slate-200'}`}>
              <p className={`text-xs font-semibold ${mine ? 'text-white/85' : 'text-brand-700'}`}>
                {who}
              </p>
              <p className="mt-1 whitespace-pre-wrap break-words">{m.body}</p>
              <time dateTime={m.created_at} className={`mt-1 block text-xs ${mine
                ? 'text-white/75' : 'text-slate-600'}`}>
                {formatISTExact(m.created_at)}
              </time>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

function ReplyBox({ ticket, token, onNewTicket }: { ticket: CustomerTicket; token: string;
  onNewTicket: (write: CustomerWrite) => void }) {
  const reply = useCustomerReply(token)
  const [body, setBody] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)
  const id = useId()
  const waiting = ticket.status === 'waiting_on_customer'

  useEffect(() => {
    if (waiting) ref.current?.focus({ preventScroll: true })
  }, [waiting])

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    const text = body.trim()
    if (!text) return
    reply.mutate(text, { onSuccess: (write) => {
      setBody('')
      if (write.new_ticket_link) onNewTicket(write)
    } })
  }

  const label = waiting ? 'We are waiting for your answer'
    : ticket.message_starts_new_ticket ? 'Write to us (starts a new request)'
      : 'Write a reply'
  const error = reply.error
  const message = !error ? null
    : isApiError(error) && error.status === 429 ? 'Too many messages — wait a minute.'
      : isApiError(error) ? error.message : 'Could not send. Please try again.'

  return (
    <form onSubmit={onSubmit} className={`rounded-2xl bg-white p-3 shadow-lg ring-1 sm:p-4 ${waiting
      ? 'ring-2 ring-amber-500' : 'ring-slate-200'}`}>
      <label htmlFor={id} className={`block text-sm font-semibold ${waiting ? 'text-amber-900'
        : 'text-navy-900'}`}>
        {label}
      </label>
      {ticket.message_starts_new_ticket && (
        <p className="mt-1 text-xs text-slate-600">
          This request is closed. Your message will open a new request with its own link.
        </p>
      )}
      <div className="mt-2 flex items-end gap-2">
        <textarea id={id} ref={ref} rows={2} maxLength={10000} value={body}
          onChange={(e) => setBody(e.target.value)} placeholder="Type your message…"
          className="block max-h-[35dvh] min-h-12 w-full flex-1 resize-y rounded-xl border-0
            bg-slate-50 px-3 py-2.5 text-base text-navy-900 ring-1 ring-inset ring-slate-300
            focus:ring-2 focus:ring-brand-600" />
        <Button type="submit" size="lg" busy={reply.isPending} disabled={!body.trim()}
          aria-label="Send message" className="shrink-0 px-4">
          <SendIcon className="size-5" />
          <span className="hidden sm:inline">Send</span>
        </Button>
      </div>
      {message && <p role="alert" className="mt-2 text-sm text-red-800">{message}</p>}
    </form>
  )
}

function TicketView({ token }: { token: string }) {
  const query = useCustomerTicket(token)
  const reopen = useReopen(token)
  const [followUp, setFollowUp] = useState<CustomerWrite | null>(null)
  usePageTitle(query.data ? `Your request ${ticketNumber(query.data.number)}` : 'Your request',
    'Arvo Systems support')

  if (query.isPending) return <CustomerShell><PageSkeleton rows={4} /></CustomerShell>
  if (query.isError) {
    if (isApiError(query.error) && query.error.status === 404) return <InvalidLink />
    return (
      <CustomerShell>
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </CustomerShell>
    )
  }
  const ticket = query.data

  return (
    <CustomerShell>
      <div className="space-y-4">
        <header className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-sm font-semibold text-slate-600">
              {ticketNumber(ticket.number)}
            </span>
            <CopyButton text={window.location.href} variant="secondary" label="Copy link" />
          </div>
          <h1 className="mt-2 break-words text-xl font-semibold">{ticket.subject}</h1>
          <p className={`mt-3 inline-block rounded-2xl px-3 py-1.5 text-sm font-semibold
            ${STATUS_TONE[ticket.status]}`} aria-live="polite">
            {customerStatusLabel(ticket)}
          </p>
          {ticket.can_reopen && (
            <div className="mt-3">
              <Button variant="secondary" busy={reopen.isPending} onClick={() => reopen.mutate()}>
                Not fixed? Reopen this request
              </Button>
              {reopen.error && (
                <p role="alert" className="mt-2 flex items-start gap-2 text-sm text-red-800">
                  <AlertIcon className="mt-0.5 size-4 shrink-0" />
                  {isApiError(reopen.error) ? reopen.error.message : 'Could not reopen.'}
                </p>
              )}
            </div>
          )}
          <p className="mt-3 text-xs text-slate-600">
            Keep this page's link private — anyone with it can read and reply.
          </p>
        </header>

        {followUp?.new_ticket_link && (
          <section aria-live="polite" className="rounded-2xl bg-white p-4 shadow-sm ring-1
            ring-slate-200 sm:p-5">
            <h2 className="font-semibold">
              We opened a new request
              {followUp.new_ticket_number ? `: ${ticketNumber(followUp.new_ticket_number)}` : ''}
            </h2>
            <p className="mt-1 text-sm">Your message started a new request. Use this new link
              from now on — it is shown only once.</p>
            <div className="mt-3"><SecretLink link={followUp.new_ticket_link} audience="customer" /></div>
            <a href={followUp.new_ticket_link} className={buttonClass('secondary', 'md', 'mt-3')}>
              Open the new request
            </a>
          </section>
        )}

        <section aria-label="Messages" className="pb-2">
          <Thread ticket={ticket} />
        </section>

        <div className="sticky bottom-0 z-10 -mx-4 bg-linear-to-t from-slate-50 via-slate-50
          to-transparent px-4 pb-3 pt-4">
          <ReplyBox ticket={ticket} token={token}
            onNewTicket={(write) => { setFollowUp(write); window.scrollTo({ top: 0 }) }} />
        </div>
      </div>
    </CustomerShell>
  )
}

export default function CustomerTicketPage() {
  const { hash } = useLocation()
  const token = readToken(hash)
  if (!token) return <InvalidLink />
  // key: a different link in the same tab starts from a clean state.
  return <TicketView key={token} token={token} />
}
