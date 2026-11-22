import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { request } from '../../api/client'
import { authKeys } from '../../api/keys'

/** The signed-in agent (GET /api/auth/me). 401 → not signed in (guards redirect). */
export function useMe() {
  return useQuery({
    queryKey: authKeys.me,
    queryFn: ({ signal }) => request('get', '/api/auth/me', { signal }),
    staleTime: 60_000,
    retry: false,
    meta: { silentErrors: true },
  })
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      request('post', '/api/auth/login', { body }),
    onSuccess: (agent) => {
      queryClient.clear()
      queryClient.setQueryData(authKeys.me, agent)
    },
    meta: { silentErrors: true },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => request('post', '/api/auth/logout'),
    onSettled: () => queryClient.clear(),
  })
}

/** `next` from /login?next=… — only same-site paths (no open redirect). */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) {
    return '/tickets'
  }
  return next
}
