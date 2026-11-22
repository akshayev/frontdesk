/** UI-6 actions, rendered ONLY from the server's allowed_actions (D-037). Every call sends the
 * ticket's current version (CLM-3); results come from the server (no optimistic updates). */
import { useState } from 'react'
import { isApiError } from '../../../api/errors'
import type { Action, Priority, TicketDetail } from '../../../api/types'
import { Button } from '../../../components/ui/Button'
import { buttonClass } from '../../../components/ui/buttonClass'
import { Dialog } from '../../../components/ui/Dialog'
import { SelectField } from '../../../components/ui/Field'
import { DownloadIcon } from '../../../components/ui/Icon'
import { PRIORITIES, PRIORITY_LABEL } from '../../../lib/labels'
import { transcriptUrl, useAgents, useAssign, useChangePriority, useClaim, useRelease,
  useResolve } from '../queries'

/** Errors the global policy does not already toast (already_claimed, 403, 429, 5xx). */
function inlineMessage(...errors: unknown[]): string | null {
  for (const error of errors) {
    if (!isApiError(error)) continue
    if (error.code === 'already_claimed' || error.status === 403 || error.status === 429 ||
      error.status >= 500 || error.status === 0) continue
    return error.message
  }
  return null
}

export function ActionsPanel({ detail }: { detail: TicketDetail }) {
  const id = detail.ticket.id
  const version = detail.version
  const allowed = new Set(detail.allowed_actions as Action[])
  const claim = useClaim(id)
  const release = useRelease(id)
  const resolve = useResolve(id)
  const priority = useChangePriority(id)
  const assign = useAssign(id)
  const [newPriority, setNewPriority] = useState<Priority>(detail.ticket.priority)
  const [confirmPriority, setConfirmPriority] = useState(false)
  const [assigning, setAssigning] = useState(false)

  // Mine and open, but no public reply yet → Resolve is shown disabled with the reason (D-027).
  const resolveBlocked = !allowed.has('resolve') && allowed.has('reply') &&
    detail.ticket.first_response_at === null
  const message = inlineMessage(claim.error, release.error, resolve.error, priority.error,
    assign.error)

  return (
    <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 lg:p-5"
      aria-labelledby="actions-h">
      <h2 id="actions-h" className="text-base font-semibold">Actions</h2>
      <div className="mt-3 flex flex-col gap-2">
        {allowed.has('claim') && (
          <Button size="lg" onClick={() => claim.mutate()} busy={claim.isPending}>
            Take this ticket
          </Button>
        )}
        {(allowed.has('resolve') || resolveBlocked) && (
          <div>
            <Button className="w-full" variant="secondary" disabled={resolveBlocked}
              busy={resolve.isPending} onClick={() => resolve.mutate(version)}
              aria-describedby={resolveBlocked ? 'resolve-why' : undefined}>
              Resolve
            </Button>
            {resolveBlocked && (
              <p id="resolve-why" className="mt-1 text-xs text-slate-600">
                Reply to the customer before resolving.
              </p>
            )}
          </div>
        )}
        {allowed.has('change_priority') && (
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <SelectField label="Priority" value={newPriority}
                onChange={(e) => setNewPriority(e.target.value as Priority)}>
                {PRIORITIES.map((p) => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
              </SelectField>
            </div>
            <Button variant="secondary" disabled={newPriority === detail.ticket.priority}
              onClick={() => setConfirmPriority(true)}>
              Change
            </Button>
          </div>
        )}
        {allowed.has('assign') && (
          <Button variant="secondary" onClick={() => setAssigning(true)}>Assign…</Button>
        )}
        {allowed.has('release') && (
          <Button variant="ghost" onClick={() => release.mutate(version)} busy={release.isPending}>
            Release ticket
          </Button>
        )}
        <a href={transcriptUrl(id)} download className={buttonClass('ghost', 'md')}>
          <DownloadIcon className="size-4" /> Download transcript (CSV)
        </a>
      </div>
      {message && <p role="alert" className="mt-3 text-sm text-red-800">{message}</p>}

      <Dialog open={confirmPriority} size="sm" title="Change priority?"
        onClose={() => setConfirmPriority(false)}
        actions={<>
          <Button variant="secondary" onClick={() => setConfirmPriority(false)}>Cancel</Button>
          <Button busy={priority.isPending} onClick={() => priority.mutate(
            { priority: newPriority, version },
            { onSettled: () => setConfirmPriority(false) })}>
            Change to {PRIORITY_LABEL[newPriority]}
          </Button>
        </>}>
        <p>
          {PRIORITY_LABEL[detail.ticket.priority]} → <strong>{PRIORITY_LABEL[newPriority]}</strong>.
          Unmet due times are recalculated: an upgrade can only bring them closer, a downgrade
          counts from when the ticket was created. Met targets stay met. This is recorded in the
          history.
        </p>
      </Dialog>

      {allowed.has('assign') && (
        <AssignDialog open={assigning} onClose={() => setAssigning(false)}
          currentId={detail.ticket.assignee?.id ?? null}
          busy={assign.isPending}
          onAssign={(agentId) => assign.mutate({ agentId, version },
            { onSettled: () => setAssigning(false) })} />
      )}
    </section>
  )
}

function AssignDialog({ open, onClose, currentId, onAssign, busy }: { open: boolean;
  onClose: () => void; currentId: string | null; onAssign: (agentId: string) => void;
  busy: boolean }) {
  const agents = useAgents(open)
  const [picked, setPicked] = useState('')
  const options = agents.data ?? []
  const value = picked || options.find((a) => a.id !== currentId)?.id || ''
  return (
    <Dialog open={open} size="sm" title="Assign ticket" onClose={onClose}
      actions={<>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button disabled={!value || value === currentId} busy={busy}
          onClick={() => onAssign(value)}>Assign</Button>
      </>}>
      {agents.isPending && <p>Loading agents…</p>}
      {agents.isError && <p role="alert" className="text-red-800">Could not load the agents.</p>}
      {agents.isSuccess && (
        <SelectField label="Assign to" value={value} onChange={(e) => setPicked(e.target.value)}>
          {options.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}{a.role === 'lead' ? ' (lead)' : ''}{a.id === currentId ? ' — current' : ''}
            </option>
          ))}
        </SelectField>
      )}
    </Dialog>
  )
}
