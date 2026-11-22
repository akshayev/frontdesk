/**
 * UI-5 / D-033 composer: two separate buttons — "Reply to customer" (indigo) and "Add internal
 * note" (yellow) — never a toggle. Note mode turns the whole box yellow with a lock icon, the
 * banner "Internal note — only your team can see this" and the button "Save internal note".
 * Reply and note keep SEPARATE drafts, so text written as a note can never be sent to the
 * customer by switching modes (INC-0304). On 409 stale_version the draft is kept and a
 * collision banner asks the agent to review the refreshed ticket (CLM-3).
 */
import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { hasCode, isApiError } from '../../../api/errors'
import { Button } from '../../../components/ui/Button'
import { AlertIcon, LockIcon, SendIcon } from '../../../components/ui/Icon'
import { useAddNote, useReply } from '../queries'

export type ComposerMode = 'reply' | 'note'

type Props = {
  ticketId: string
  version: number
  customerName: string
  canReply: boolean
  canWait: boolean
}

const INLINE_CODES = ['reply_required', 'illegal_transition', 'forbidden', 'validation_error']

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

export function Composer({ ticketId, version, customerName, canReply, canWait }: Props) {
  const [mode, setMode] = useState<ComposerMode | null>(null)
  const [drafts, setDrafts] = useState<Record<ComposerMode, string>>({ reply: '', note: '' })
  const [wait, setWait] = useState(false)
  const [collision, setCollision] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const textareaId = useId()
  const reply = useReply(ticketId)
  const note = useAddNote(ticketId)
  const active = mode === 'note' ? note : reply
  const effectiveMode: ComposerMode | null = mode === 'reply' && !canReply ? null : mode

  function open(next: ComposerMode) {
    setMode(next)
    reply.reset()
    note.reset()
    window.requestAnimationFrame(() => textareaRef.current?.focus())
  }

  // R / N shortcuts — only when the agent is not typing somewhere.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey || isTypingTarget(event.target)) return
      const key = event.key.toLowerCase()
      if (key === 'r' && canReply) { event.preventDefault(); open('reply') }
      if (key === 'n') { event.preventDefault(); open('note') }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  })

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!effectiveMode) return
    const body = drafts[effectiveMode].trim()
    if (!body) return
    const done = {
      onSuccess: () => {
        setDrafts((d) => ({ ...d, [effectiveMode]: '' }))
        setCollision(false)
        setWait(false)
        setMode(null)
      },
      onError: (error: unknown) => {
        if (hasCode(error, 'stale_version')) setCollision(true)
      },
    }
    if (effectiveMode === 'note') note.mutate({ body, version }, done)
    else reply.mutate({ body, version, wait: canWait && wait }, done)
  }

  const error = active.error
  const inlineError = isApiError(error) && error.status === 409 && error.code !== 'stale_version'
    || hasCode(error, ...INLINE_CODES) ? error : null
  const isNote = effectiveMode === 'note'

  return (
    <section aria-label="Write to the customer or your team"
      className="rounded-2xl bg-white p-3 shadow-lg ring-1 ring-slate-200 sm:p-4">
      <div className="flex flex-wrap gap-2">
        {canReply && (
          <button type="button" onClick={() => open('reply')} aria-pressed={effectiveMode === 'reply'}
            className={`inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold
              ring-2 ring-inset transition-colors ${effectiveMode === 'reply'
                ? 'bg-brand-600 text-white ring-brand-600'
                : 'bg-white text-brand-700 ring-brand-600 hover:bg-brand-50'}`}>
            <SendIcon className="size-4" /> Reply to customer
            <kbd className="hidden rounded border border-current px-1 text-[10px] opacity-70
              lg:inline">R</kbd>
          </button>
        )}
        <button type="button" onClick={() => open('note')} aria-pressed={isNote}
          className={`inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold
            ring-2 ring-inset ring-amber-500 transition-colors ${isNote
              ? 'bg-amber-300 text-amber-950'
              : 'bg-amber-50 text-amber-900 hover:bg-amber-100'}`}>
          <LockIcon className="size-4" /> Add internal note
          <kbd className="hidden rounded border border-current px-1 text-[10px] opacity-70
            lg:inline">N</kbd>
        </button>
      </div>
      {!canReply && (
        <p className="mt-2 text-xs text-slate-600">
          Only the agent who owns this ticket can reply to the customer.
        </p>
      )}

      {collision && (
        <div role="alert" className="mt-3 flex items-start gap-2 rounded-xl bg-orange-50 p-3 text-sm
          text-orange-950 ring-1 ring-orange-300">
          <AlertIcon className="mt-0.5 size-4 shrink-0" />
          <div className="flex-1">
            <p className="font-semibold">This ticket changed while you were writing.</p>
            <p>Review the latest activity above — your text is kept. Then send again.</p>
          </div>
          <button type="button" className="text-sm font-semibold underline"
            onClick={() => setCollision(false)}>Dismiss</button>
        </div>
      )}

      {effectiveMode && (
        <form onSubmit={onSubmit} className={`mt-3 rounded-2xl p-3 ${isNote
          ? 'border-2 border-amber-500 bg-amber-100'
          : 'border-2 border-brand-200 bg-brand-50/40'}`}>
          {isNote ? (
            <p role="status" className="mb-2 flex items-center gap-2 rounded-xl bg-amber-300 px-3 py-2
              text-sm font-semibold text-amber-950">
              <LockIcon className="size-4" title="Private" />
              Internal note — only your team can see this
            </p>
          ) : (
            <p className="mb-2 text-sm font-semibold text-brand-800">
              Reply to {customerName} — the customer will see this message.
            </p>
          )}
          <label htmlFor={textareaId} className="sr-only">
            {isNote ? 'Internal note' : `Reply to ${customerName}`}
          </label>
          <textarea id={textareaId} ref={textareaRef} rows={4} maxLength={10000}
            value={drafts[effectiveMode]}
            onChange={(e) => setDrafts((d) => ({ ...d, [effectiveMode]: e.target.value }))}
            placeholder={isNote ? 'Write a note for your team…' : 'Write your reply…'}
            className={`block max-h-[40dvh] min-h-24 w-full resize-y rounded-xl border-0 px-3
              py-2.5 text-base text-navy-900 ring-1 ring-inset focus:ring-2 ${isNote
                ? 'bg-amber-50 ring-amber-400 focus:ring-amber-600'
                : 'bg-white ring-slate-300 focus:ring-brand-600'}`} />
          {inlineError && (
            <p role="alert" className="mt-2 text-sm text-red-800">{inlineError.message}</p>
          )}
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            {!isNote && canWait ? (
              <label className="flex min-h-11 items-center gap-2 text-sm">
                <input type="checkbox" checked={wait} onChange={(e) => setWait(e.target.checked)}
                  className="size-5 rounded accent-brand-600" />
                and wait for the customer's answer
              </label>
            ) : <span />}
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setMode(null)}>Cancel</Button>
              <Button type="submit" variant={isNote ? 'note' : 'primary'} busy={active.isPending}
                disabled={!drafts[effectiveMode].trim()}>
                {isNote ? <><LockIcon className="size-4" /> Save internal note</>
                  : <><SendIcon className="size-4" /> Send to customer</>}
              </Button>
            </div>
          </div>
        </form>
      )}
    </section>
  )
}
