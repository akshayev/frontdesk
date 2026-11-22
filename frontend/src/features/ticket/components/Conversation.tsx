/** UI-4: public messages and internal notes interleaved by time. Notes are strong yellow with a
 * lock icon and the "Internal note" label (D-033). Bodies render as plain text. */
import type { Message, Note } from '../../../api/types'
import { LockIcon } from '../../../components/ui/Icon'
import { formatISTExact } from '../../../lib/format'

type Entry =
  | { kind: 'message'; at: string; id: string; item: Message }
  | { kind: 'note'; at: string; id: string; item: Note }

function interleave(messages: Message[], notes: Note[]): Entry[] {
  const entries: Entry[] = [
    ...messages.map((m) => ({ kind: 'message' as const, at: m.created_at, id: m.id, item: m })),
    ...notes.map((n) => ({ kind: 'note' as const, at: n.created_at, id: n.id, item: n })),
  ]
  return entries.sort((a, b) => Date.parse(a.at) - Date.parse(b.at))
}

function Body({ text }: { text: string }) {
  return <p className="mt-2 whitespace-pre-wrap break-words text-navy-900">{text}</p>
}

export function Conversation({ messages, notes, customerName }: { messages: Message[];
  notes: Note[]; customerName: string }) {
  const entries = interleave(messages, notes)
  if (entries.length === 0) return <p className="text-sm">No messages yet.</p>
  return (
    <ol className="space-y-3" aria-label="Conversation">
      {entries.map((entry) => {
        if (entry.kind === 'note') {
          const n = entry.item
          return (
            <li key={`n-${entry.id}`} className="rounded-2xl border-2 border-amber-500 bg-amber-100
              p-4">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-300 px-2 py-0.5
                  text-xs font-bold uppercase tracking-wide text-amber-950">
                  <LockIcon className="size-3.5" /> Internal note
                </span>
                <span className="font-semibold text-amber-950">{n.author.name}</span>
                <time dateTime={n.created_at} className="text-amber-900">
                  {formatISTExact(n.created_at)}
                </time>
              </div>
              <Body text={n.body} />
            </li>
          )
        }
        const m = entry.item
        const fromCustomer = m.author_type === 'customer'
        return (
          <li key={`m-${entry.id}`} className={`rounded-2xl p-4 ring-1 ${fromCustomer
            ? 'mr-4 bg-white ring-slate-200 sm:mr-12'
            : 'ml-4 bg-brand-50 ring-brand-200 sm:ml-12'}`}>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
              <span className="font-semibold text-navy-900">
                {fromCustomer ? customerName : (m.author?.name ?? 'Support')}
              </span>
              <span className="text-xs text-slate-600">
                {fromCustomer ? 'Customer' : 'Reply to customer'}
              </span>
              <time dateTime={m.created_at} className="text-slate-600">
                {formatISTExact(m.created_at)}
              </time>
            </div>
            <Body text={m.body} />
          </li>
        )
      })}
    </ol>
  )
}
