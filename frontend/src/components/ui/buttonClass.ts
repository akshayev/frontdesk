/** Pill button classes (D-036), shared by <Button> and links styled as buttons. */
export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'note' | 'ghost' | 'onDark'
export type ButtonSize = 'sm' | 'md' | 'lg'

const VARIANT: Record<ButtonVariant, string> = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-200',
  secondary: 'bg-white text-navy-900 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 ' +
    'disabled:text-slate-400',
  danger: 'bg-red-700 text-white hover:bg-red-800 disabled:bg-red-300',
  note: 'bg-amber-300 text-amber-950 ring-1 ring-inset ring-amber-500 hover:bg-amber-400 ' +
    'disabled:bg-amber-100',
  ghost: 'text-brand-700 hover:bg-brand-50 disabled:text-slate-400',
  onDark: 'text-white ring-1 ring-inset ring-white/40 hover:bg-white/10',
}

// Tap targets ≥ 44px (D-030) for md/lg; sm is for dense desktop toolbars only.
const SIZE: Record<ButtonSize, string> = {
  sm: 'min-h-9 px-3 text-sm',
  md: 'min-h-11 px-5 text-sm',
  lg: 'min-h-12 px-6 text-base',
}

export function buttonClass(variant: ButtonVariant = 'primary', size: ButtonSize = 'md',
  extra = ''): string {
  return [
    'inline-flex items-center justify-center gap-2 rounded-full font-semibold transition-colors',
    'disabled:cursor-not-allowed select-none',
    VARIANT[variant], SIZE[size], extra,
  ].join(' ')
}
