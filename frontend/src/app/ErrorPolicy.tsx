/** The global error policy (D-037), applied to every query and mutation error. Screens handle
 * the inline cases themselves (stale_version banner, reply_required, illegal_transition,
 * reopen_window_expired, validation); this component does the rest. */
import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useNavigate } from 'react-router'
import { isApiError, NETWORK_ERROR, ownerName } from '../api/errors'
import { ticketKeys } from '../api/keys'
import { useToast } from '../components/ui/toastContext'
import { isAgentPath } from './paths'
import { errorBus } from './queryClient'

export function ErrorPolicy() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const toast = useToast()

  useEffect(() => errorBus.subscribe(({ kind, error, silent }) => {
    if (!isApiError(error)) return
    const path = window.location.pathname
    if (error.status === 401 && isAgentPath(path)) {
      queryClient.clear()
      const next = encodeURIComponent(path + window.location.search)
      navigate(`/login?next=${next}`, { replace: true })
      return
    }
    if (error.status === 429) {
      toast.show({ tone: 'error', message: 'Too many requests — wait a minute.' })
      return
    }
    if (silent) return
    if (kind === 'mutation' && error.status === 409) {
      void queryClient.invalidateQueries({ queryKey: ticketKeys.all })
      if (error.code === 'already_claimed') {
        toast.show({ tone: 'error', message: `Already taken by ${ownerName(error)}` })
      }
      return
    }
    if (kind === 'mutation' && error.status === 403) {
      toast.show({ tone: 'error', message: "You don't have access to do that." })
      return
    }
    if (kind === 'mutation' && (error.status >= 500 || error.code === NETWORK_ERROR)) {
      toast.show({ tone: 'error', message: error.message, requestId: error.requestId })
    }
  }), [queryClient, navigate, toast])

  return null
}
