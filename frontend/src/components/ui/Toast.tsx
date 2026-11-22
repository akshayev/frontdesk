/** Toasts in aria-live regions (errors assertive, everything else polite). */
import { useCallback, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { CloseIcon } from './Icon'
import { ToastContext } from './toastContext'
import type { ToastInput, ToastTone } from './toastContext'

type ToastItem = ToastInput & { id: number }
const TIMEOUT_MS = 6000

const TONE: Record<ToastTone, string> = {
  info: 'bg-navy-900 text-white',
  success: 'bg-emerald-800 text-white',
  error: 'bg-red-800 text-white',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((t) => t.id !== id))
  }, [])

  const show = useCallback((toast: ToastInput) => {
    const id = nextId.current++
    setItems((current) => {
      // The same message twice in a row (e.g. two failing polls) is shown once.
      if (current.some((t) => t.message === toast.message)) return current
      return [...current.slice(-2), { ...toast, id }]
    })
    window.setTimeout(() => dismiss(id), TIMEOUT_MS)
  }, [dismiss])

  const api = useMemo(() => ({ show }), [show])
  const render = (tone: 'error' | 'other') => items
    .filter((t) => (tone === 'error') === (t.tone === 'error'))
    .map((t) => (
      <div key={t.id} className={`pointer-events-auto flex items-start gap-3 rounded-2xl px-4
        py-3 text-sm shadow-lg ${TONE[t.tone]}`}>
        <div className="min-w-0 flex-1">
          <p>{t.message}</p>
          {t.requestId && <p className="mt-1 text-xs opacity-80">Request id: {t.requestId}</p>}
        </div>
        <button type="button" onClick={() => dismiss(t.id)} aria-label="Dismiss message"
          className="-m-1 rounded-full p-1 hover:bg-white/15">
          <CloseIcon className="size-4" />
        </button>
      </div>
    ))

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center
        gap-2 p-4 sm:items-end">
        <div aria-live="assertive" role="alert" className="flex w-full max-w-sm flex-col gap-2">
          {render('error')}
        </div>
        <div aria-live="polite" role="status" className="flex w-full max-w-sm flex-col gap-2">
          {render('other')}
        </div>
      </div>
    </ToastContext.Provider>
  )
}
