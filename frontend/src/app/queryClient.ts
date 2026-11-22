/**
 * TanStack Query setup (D-037): server is authoritative, retry off for 4xx, no background
 * polling. Every query/mutation error is also published on `errorBus`, which <ErrorPolicy/>
 * (inside the router) turns into redirects and toasts — the global error policy.
 */
import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { isClientError } from '../api/errors'

export type ErrorSource = { kind: 'query' | 'mutation'; error: unknown; silent: boolean }
type Listener = (event: ErrorSource) => void

const listeners = new Set<Listener>()

export const errorBus = {
  emit(event: ErrorSource): void {
    listeners.forEach((listener) => listener(event))
  },
  subscribe(listener: Listener): () => void {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
}

/** Set `meta: { silentErrors: true }` when the screen shows the error itself. */
type Meta = Record<string, unknown> | undefined
const silent = (meta: Meta): boolean => meta?.silentErrors === true

export function createQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => errorBus.emit({ kind: 'query', error,
        silent: silent(query.meta) }),
    }),
    mutationCache: new MutationCache({
      onError: (error, _vars, _ctx, mutation) => errorBus.emit({ kind: 'mutation', error,
        silent: silent(mutation.meta) }),
    }),
    defaultOptions: {
      queries: {
        retry: (count, error) => !isClientError(error) && count < 2,
        refetchOnWindowFocus: true,
        refetchIntervalInBackground: false,
        staleTime: 5_000,
      },
      mutations: { retry: false },
    },
  })
}
