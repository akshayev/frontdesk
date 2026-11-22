import { useQuery } from '@tanstack/react-query'
import { request } from '../../api/client'
import { reportKeys } from '../../api/keys'

/** RPT-1 late tickets (lead). */
export function useLateReport() {
  return useQuery({
    queryKey: reportKeys.late(),
    queryFn: ({ signal }) => request('get', '/api/lead/reports/late', { signal }),
    refetchInterval: 60_000,
  })
}

/** AUD-3: recompute the whole hash chain — only when the lead asks (not polled). */
export function useAuditVerify() {
  return useQuery({
    queryKey: reportKeys.verify(),
    queryFn: ({ signal }) => request('get', '/api/lead/audit/verify', { signal }),
    enabled: false,
    retry: false,
    staleTime: 0,
    gcTime: 0,
    meta: { silentErrors: true },
  })
}

export const LATE_CSV_URL = '/api/lead/reports/late.csv'
