import { useMutation } from '@tanstack/react-query'
import { request } from '../../api/client'
import type { PublicTicketIn } from '../../api/types'

/** IN-1 "Submit a problem": the secret link comes back once. */
export function useSubmitRequest() {
  return useMutation({
    mutationFn: (body: PublicTicketIn) => request('post', '/api/public/tickets', { body }),
    meta: { silentErrors: true },
  })
}
