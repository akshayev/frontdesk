/** View switcher: underlined tabs on desktop, horizontally scrollable chips on phones. */
import { useRef } from 'react'
import type { KeyboardEvent } from 'react'

type Item<T extends string> = { id: T; label: string }

export function Tabs<T extends string>({ items, value, onChange, label }: {
  items: readonly Item<T>[]; value: T; onChange: (id: T) => void; label: string }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (!delta) return
    event.preventDefault()
    const next = (index + delta + items.length) % items.length
    const item = items[next]
    if (!item) return
    onChange(item.id)
    refs.current[next]?.focus()
  }

  return (
    <div role="tablist" aria-label={label}
      className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 md:mx-0 md:gap-1 md:overflow-visible
        md:border-b md:border-slate-200 md:px-0 md:pb-0">
      {items.map((item, index) => {
        const selected = item.id === value
        return (
          <button key={item.id} type="button" role="tab" aria-selected={selected}
            tabIndex={selected ? 0 : -1} ref={(el) => { refs.current[index] = el }}
            onClick={() => onChange(item.id)} onKeyDown={(e) => onKeyDown(e, index)}
            className={`min-h-11 shrink-0 whitespace-nowrap rounded-full px-4 text-sm font-semibold
              md:-mb-px md:rounded-none md:border-b-2 md:px-4
              ${selected
                ? 'bg-brand-600 text-white md:border-brand-600 md:bg-transparent md:text-brand-700'
                : 'bg-white text-ink ring-1 ring-slate-200 md:border-transparent md:bg-transparent ' +
                  'md:ring-0 md:hover:text-navy-900'}`}>
            {item.label}
          </button>
        )
      })}
    </div>
  )
}
