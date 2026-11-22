import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { buttonClass } from './buttonClass'
import type { ButtonSize, ButtonVariant } from './buttonClass'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: ButtonSize
  busy?: boolean
  children: ReactNode
}

export function Button({ variant = 'primary', size = 'md', busy = false, className = '',
  type = 'button', disabled, children, ...rest }: Props) {
  return (
    <button type={type} className={buttonClass(variant, size, className)}
      disabled={disabled || busy} aria-busy={busy || undefined} {...rest}>
      {busy && <span className="size-4 animate-spin rounded-full border-2 border-current
        border-r-transparent" aria-hidden="true" />}
      {children}
    </button>
  )
}
