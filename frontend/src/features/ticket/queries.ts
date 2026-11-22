/**
 * Ticket page data and actions. Every mutation sends expected_version (CLM-3) and returns the
 * fresh ticket page from the server; there are NO optimistic updates (D-037): the cache is set
 * from the server's answer, then every ticket query is invalidated.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { request } from '../../api/client'
import { leadKeys, POLL, ticketKeys } from '../../api/keys'
import type { Priority, TicketDetail } from '../../api/types'

export function useTicket(id: string) {
  return useQuery({
    queryKey: ticketKeys.detail(id),
    queryFn: ({ signal }) => request('get', '/api/agent/tickets/{ticket_id}', {
      path: { ticket_id: id }, signal }),
    refetchInterval: POLL.detail,
  })
}

/** Lead's assign dialog (D-040): id, name, role only. */
export function useAgents(enabled: boolean) {
  return useQuery({
    queryKey: leadKeys.agents,
    queryFn: ({ signal }) => request('get', '/api/lead/agents', { signal }),
    enabled,
    staleTime: 5 * 60_000,
  })
}

function useTicketMutation<V>(id: string, call: (vars: V) => Promise<TicketDetail>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: (detail) => {
      queryClient.setQueryData(ticketKeys.detail(id), detail)
      void queryClient.invalidateQueries({ queryKey: ticketKeys.all })
    },
  })
}

const path = (id: string) => ({ ticket_id: id })

export function useClaim(id: string) {
  return useTicketMutation(id, () =>
    request('post', '/api/agent/tickets/{ticket_id}/claim', { path: path(id) }))
}

export function useRelease(id: string) {
  return useTicketMutation(id, (version: number) =>
    request('post', '/api/agent/tickets/{ticket_id}/release', {
      path: path(id), body: { expected_version: version } }))
}

export type ReplyVars = { body: string; version: number; wait: boolean }

/** UI-5 "Reply to customer" (+ "and wait for the customer's answer", WAIT-2). */
export function useReply(id: string) {
  return useTicketMutation(id, ({ body, version, wait }: ReplyVars) =>
    request('post', '/api/agent/tickets/{ticket_id}/replies', {
      path: path(id), body: { body, expected_version: version, wait_for_customer: wait } }))
}

export type NoteVars = { body: string; version: number }

/** UI-5 internal note (LEAK-1: never shown to the customer). */
export function useAddNote(id: string) {
  return useTicketMutation(id, ({ body, version }: NoteVars) =>
    request('post', '/api/agent/tickets/{ticket_id}/notes', {
      path: path(id), body: { body, expected_version: version } }))
}

export function useResolve(id: string) {
  return useTicketMutation(id, (version: number) =>
    request('post', '/api/agent/tickets/{ticket_id}/resolve', {
      path: path(id), body: { expected_version: version } }))
}

export function useChangePriority(id: string) {
  return useTicketMutation(id, ({ priority, version }: { priority: Priority; version: number }) =>
    request('patch', '/api/agent/tickets/{ticket_id}/priority', {
      path: path(id), body: { priority, expected_version: version } }))
}

export function useAssign(id: string) {
  return useTicketMutation(id, ({ agentId, version }: { agentId: string; version: number }) =>
    request('post', '/api/lead/tickets/{ticket_id}/assign', {
      path: path(id), body: { agent_id: agentId, expected_version: version } }))
}

export function transcriptUrl(id: string): string {
  return `/api/agent/tickets/${encodeURIComponent(id)}/transcript.csv`
}
