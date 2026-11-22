import type { ReactNode } from 'react'
import { isApiError, NETWORK_ERROR } from '../../api/errors'
import { AlertIcon } from './Icon'
import { Button } from './Button'

function describe(error: unknown): { title: string; detail: string } {
  if (!isApiError(error)) return { title: 'Something went wrong', detail: 'Please try again.' }
  if (error.status === 403) return { title: "You don't have access", detail: error.message }
  if (error.status === 404) return { title: 'Not found', detail: error.message }
  if (error.status === 429) {
    return { title: 'Too many requests', detail: 'Too many requests — wait a minute.' }
  }
  if (error.code === NETWORK_ERROR) return { title: 'You seem to be offline', detail: error.message }
  return { title: 'Something went wrong', detail: error.message }
}

/** Error panel that always shows the request id (support can find it in the logs). */
export function ErrorState({ error, onRetry, children }: { error: unknown; onRetry?: () => void;
  children?: ReactNode }) {
  const { title, detail } = describe(error)
  const requestId = isApiError(error) ? error.requestId : null
  return (
    <div role="alert" className="rounded-2xl bg-red-50 p-5 text-red-900 ring-1 ring-red-200">
      <div className="flex items-start gap-3">
        <AlertIcon className="mt-0.5 size-5 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{title}</p>
          <p className="mt-1 text-sm">{detail}</p>
          {requestId && (
            <p className="mt-2 text-xs">
              Request id: <code className="break-all font-mono select-all">{requestId}</code>
            </p>
          )}
          {children}
          {onRetry && (
            <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
              Try again
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

/** Short inline message for a refused action (409 reply_required, illegal_transition …). */
export function InlineError({ error }: { error: unknown }) {
  if (!error) return null
  const message = isApiError(error) ? error.message : 'Something went wrong.'
  return (
    <p role="alert" className="mt-2 flex items-start gap-2 text-sm text-red-800">
      <AlertIcon className="mt-0.5 size-4 shrink-0" />
      <span>{message}</span>
    </p>
  )
}
