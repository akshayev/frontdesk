/** Labelled form controls. Every input has a visible <label> (a11y) and ≥ 16px text (D-030). */
import { useId } from 'react'
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes,
  TextareaHTMLAttributes } from 'react'

export const inputClass = 'block w-full rounded-xl border-0 bg-white px-3.5 py-2.5 text-base ' +
  'text-navy-900 shadow-sm ring-1 ring-inset ring-slate-300 placeholder:text-slate-400 ' +
  'focus:ring-2 focus:ring-brand-600 disabled:bg-slate-100'

function Wrapper({ id, label, hint, children }: { id: string; label: ReactNode; hint?: ReactNode;
  children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-semibold text-navy-900">
        {label}
      </label>
      {children}
      {hint && <p id={`${id}-hint`} className="mt-1 text-xs text-slate-600">{hint}</p>}
    </div>
  )
}

type Labelled = { label: ReactNode; hint?: ReactNode }

export function TextField({ label, hint, className = '', ...rest }:
  Labelled & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId()
  return (
    <Wrapper id={id} label={label} hint={hint}>
      <input id={id} aria-describedby={hint ? `${id}-hint` : undefined}
        className={`${inputClass} ${className}`} {...rest} />
    </Wrapper>
  )
}

export function TextArea({ label, hint, className = '', ...rest }:
  Labelled & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId()
  return (
    <Wrapper id={id} label={label} hint={hint}>
      <textarea id={id} aria-describedby={hint ? `${id}-hint` : undefined}
        className={`${inputClass} ${className}`} {...rest} />
    </Wrapper>
  )
}

export function SelectField({ label, hint, className = '', children, ...rest }:
  Labelled & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId()
  return (
    <Wrapper id={id} label={label} hint={hint}>
      <select id={id} aria-describedby={hint ? `${id}-hint` : undefined}
        className={`${inputClass} ${className}`} {...rest}>
        {children}
      </select>
    </Wrapper>
  )
}
