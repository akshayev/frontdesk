import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { request } from '../../api/client'
import { POLL, ticketKeys } from '../../api/keys'
import type { TicketCreateIn, View } from '../../api/types'

/** UI-1 / UI-7 list view; polls every 30 s while the tab is visible. */
export function useTickets(view: View) {
  return useQuery({
    queryKey: ticketKeys.list(view),
    queryFn: ({ signal }) => request('get', '/api/agent/tickets', { query: { view }, signal }),
    refetchInterval: POLL.list,
  })
}

/** IN-2: create a ticket on behalf of a customer (the link comes back once). */
export function useCreateTicket() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TicketCreateIn) => request('post', '/api/agent/tickets', { body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ticketKeys.all }),
    meta: { silentErrors: true },
  })
}
