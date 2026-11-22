/** Query key factory (D-037). Invalidate `ticketKeys.all` after any ticket mutation. */
import type { View } from './types'

export const ticketKeys = {
  all: ['tickets'] as const,
  lists: () => [...ticketKeys.all, 'list'] as const,
  list: (view: View) => [...ticketKeys.lists(), view] as const,
  details: () => [...ticketKeys.all, 'detail'] as const,
  detail: (id: string) => [...ticketKeys.details(), id] as const,
}

export const authKeys = {
  me: ['auth', 'me'] as const,
}

export const leadKeys = {
  agents: ['lead', 'agents'] as const,
}

export const reportKeys = {
  all: ['reports'] as const,
  late: () => [...reportKeys.all, 'late'] as const,
  verify: () => [...reportKeys.all, 'audit-verify'] as const,
}

export const holidayKeys = {
  all: ['holidays'] as const,
}

/** Customer cache entries are keyed by a hash of the token, never the token itself. */
export const customerKeys = {
  all: ['customer'] as const,
  ticket: (hash: string) => [...customerKeys.all, 'ticket', hash] as const,
}

/** Non-cryptographic FNV-1a hash: only to keep the raw secret out of query keys / devtools. */
export function tokenHash(token: string): string {
  let hash = 0x811c9dc5
  for (let i = 0; i < token.length; i++) {
    hash ^= token.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash.toString(16).padStart(8, '0')
}

export const POLL = { list: 30_000, detail: 15_000, customer: 30_000 } as const
