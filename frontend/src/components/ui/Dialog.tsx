/** Modal dialog on the native <dialog> element: focus trap, Esc to close and backdrop for free. */
import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { CloseIcon } from './Icon'

type Props = {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  /** Footer buttons. */
  actions?: ReactNode
  size?: 'sm' | 'md'
}

export function Dialog({ open, title, onClose, children, actions, size = 'md' }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal()
      else dialog.setAttribute('open', '')
    } else if (!open && dialog.open) {
      if (typeof dialog.close === 'function') dialog.close()
      else dialog.removeAttribute('open')
    }
  }, [open])

  return (
    <dialog ref={ref} aria-labelledby={titleId} onClose={onClose}
      onCancel={(e) => { e.preventDefault(); onClose() }}
      className={`m-auto w-[calc(100%-2rem)] rounded-2xl bg-white p-0 text-ink shadow-xl
        ${size === 'sm' ? 'max-w-md' : 'max-w-xl'}`}>
      {open && (
        <div className="flex max-h-[85dvh] flex-col">
          <div className="flex items-center justify-between gap-4 border-b border-slate-200 px-5
            py-4">
            <h2 id={titleId} className="text-lg font-semibold">{title}</h2>
            <button type="button" onClick={onClose} aria-label="Close dialog"
              className="-m-2 rounded-full p-2 hover:bg-slate-100">
              <CloseIcon />
            </button>
          </div>
          <div className="overflow-y-auto px-5 py-4">{children}</div>
          {actions && (
            <div className="flex flex-wrap justify-end gap-2 border-t border-slate-200 px-5 py-4">
              {actions}
            </div>
          )}
        </div>
      )}
    </dialog>
  )
}
