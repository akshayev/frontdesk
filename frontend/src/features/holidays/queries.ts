import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { request } from '../../api/client'
import { holidayKeys, ticketKeys } from '../../api/keys'
import type { HolidayIn } from '../../api/types'

export function useHolidays() {
  return useQuery({
    queryKey: holidayKeys.all,
    queryFn: ({ signal }) => request('get', '/api/lead/holidays', { signal }),
  })
}

/** Holidays change every SLA due time, so ticket data is refetched too. */
function useInvalidate() {
  const queryClient = useQueryClient()
  return () => Promise.all([
    queryClient.invalidateQueries({ queryKey: holidayKeys.all }),
    queryClient.invalidateQueries({ queryKey: ticketKeys.all }),
  ])
}

export function useAddHoliday() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (body: HolidayIn) => request('post', '/api/lead/holidays', { body }),
    onSuccess: invalidate,
    meta: { silentErrors: true },
  })
}

export function useRemoveHoliday() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (day: string) => request('delete', '/api/lead/holidays/{day}', {
      path: { day } }),
    onSuccess: invalidate,
  })
}
