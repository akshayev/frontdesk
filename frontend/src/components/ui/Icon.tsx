/** Inline SVG icons (no icon font, no third-party origin — CSP). Decorative by default. */
import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { title?: string }

function Svg({ title, children, className = 'size-5', ...rest }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
      strokeLinecap="round" strokeLinejoin="round" className={className}
      aria-hidden={title ? undefined : true} role={title ? 'img' : undefined} {...rest}>
      {title && <title>{title}</title>}
      {children}
    </svg>
  )
}

export function LockIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </Svg>
  )
}

export function MenuIcon(props: IconProps) {
  return <Svg {...props}><path d="M4 6h16M4 12h16M4 18h16" /></Svg>
}

export function CloseIcon(props: IconProps) {
  return <Svg {...props}><path d="M6 6l12 12M18 6L6 18" /></Svg>
}

export function CopyIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15V5a2 2 0 0 1 2-2h8" />
    </Svg>
  )
}

export function CheckIcon(props: IconProps) {
  return <Svg {...props}><path d="M5 12l5 5L20 7" /></Svg>
}

export function AlertIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 3l9.5 17h-19z" />
      <path d="M12 10v4M12 17.5v.01" />
    </Svg>
  )
}

export function ChevronIcon(props: IconProps) {
  return <Svg {...props}><path d="M6 9l6 6 6-6" /></Svg>
}

export function SendIcon(props: IconProps) {
  return <Svg {...props}><path d="M4 12l16-8-6 16-2-7z" /></Svg>
}

export function DownloadIcon(props: IconProps) {
  return <Svg {...props}><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></Svg>
}

export function ShieldIcon(props: IconProps) {
  return <Svg {...props}><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /></Svg>
}
