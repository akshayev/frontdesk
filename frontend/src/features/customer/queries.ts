/**
 * Customer page data (D-038): the token comes from the URL fragment and is sent only as
 * X-Ticket-Token. Query keys hold a hash of it, never the token itself.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { request } from '../../api/client'
import { customerKeys, POLL, tokenHash } from '../../api/keys'

/** A plausible token (secrets.token_urlsafe(32) is 43 url-safe characters). */
export function readToken(hash: string): string | null {
  const token = hash.replace(/^#/, '')
  return /^[A-Za-z0-9_-]{20,256}$/.test(token) ? token : null
}

export function useCustomerTicket(token: string) {
  return useQuery({
    queryKey: customerKeys.ticket(tokenHash(token)),
    queryFn: ({ signal }) => request('get', '/api/customer/ticket', { token, signal }),
    refetchInterval: POLL.customer,
    meta: { silentErrors: true },
  })
}

export function useCustomerReply(token: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: string) => request('post', '/api/customer/ticket/messages', {
      token, body: { body } }),
    onSuccess: () => queryClient.invalidateQueries({
      queryKey: customerKeys.ticket(tokenHash(token)) }),
    meta: { silentErrors: true },
  })
}

export function useReopen(token: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => request('post', '/api/customer/ticket/reopen', { token }),
    onSuccess: (ticket) => queryClient.setQueryData(customerKeys.ticket(tokenHash(token)),
      ticket),
    meta: { silentErrors: true },
  })
}
