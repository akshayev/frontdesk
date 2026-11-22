/** Labelled form controls. Every input has a visible <label> (a11y) and ≥ 16px text (D-030). */
import { useEffect, useId, useLayoutEffect, useRef } from 'react'
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes,
  TextareaHTMLAttributes } from 'react'
import { EyeIcon, EyeOffIcon } from './Icon'

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

type PasswordFieldProps = Labelled & Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  /** Shown as plain text? Owned by the form, so it can hide the value again on submit. */
  visible: boolean
  onVisibleChange: (visible: boolean) => void
}

/** D-048: password input with a show/hide toggle. Only the display changes (type password ↔
 * text): value, name, autocomplete and focus stay as they are, nothing is stored or sent
 * differently. The toggle is a real button (type="button", never submits; Enter/Space work),
 * keeps the input's focus and caret on mouse/touch, and the value is hidden again when the
 * page is left (pagehide). Spellcheck/autocorrect stay off while the text is visible. */
export function PasswordField({ label, hint, className = '', visible, onVisibleChange, ...rest }:
  PasswordFieldProps) {
  const id = useId()
  const input = useRef<HTMLInputElement>(null)
  const caret = useRef<[number | null, number | null] | null>(null)

  useEffect(() => {
    const hide = () => onVisibleChange(false)
    window.addEventListener('pagehide', hide)
    return () => window.removeEventListener('pagehide', hide)
  }, [onVisibleChange])

  // Switching the input type can move the caret to the start in some browsers: restore it.
  useLayoutEffect(() => {
    const el = input.current
    const saved = caret.current
    caret.current = null
    if (el && saved && el.type === (visible ? 'text' : 'password') &&
      document.activeElement === el) el.setSelectionRange(saved[0], saved[1])
  }, [visible])

  function toggle() {
    const el = input.current
    if (el && document.activeElement === el) caret.current = [el.selectionStart, el.selectionEnd]
    onVisibleChange(!visible)
  }

  return (
    <Wrapper id={id} label={label} hint={hint}>
      <div className="relative">
        <input ref={input} id={id} type={visible ? 'text' : 'password'}
          aria-describedby={hint ? `${id}-hint` : undefined} autoCapitalize="none"
          autoCorrect="off" spellCheck={false} className={`${inputClass} pr-12 ${className}`}
          {...rest} />
        <button type="button" onClick={toggle} onMouseDown={(e) => e.preventDefault()}
          aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible}
          aria-controls={id}
          className="absolute right-0 top-0 flex size-11 items-center justify-center rounded-xl
            text-slate-600 hover:text-navy-900 focus-visible:outline-none focus-visible:ring-2
            focus-visible:ring-brand-600">
          {visible ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </div>
    </Wrapper>
  )
}
