import { createContext, useContext } from 'react'

export type ToastTone = 'info' | 'success' | 'error'
export type ToastInput = { tone: ToastTone; message: string; requestId?: string | null }
export type ToastApi = { show: (toast: ToastInput) => void }

export const ToastContext = createContext<ToastApi | null>(null)

export function useToast(): ToastApi {
  const api = useContext(ToastContext)
  if (!api) throw new Error('useToast outside ToastProvider')
  return api
}
