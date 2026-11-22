import type { ReactNode } from 'react'

export function Card({ children, className = '', as: Tag = 'section' }: {
  children: ReactNode; className?: string; as?: 'section' | 'div' | 'article' | 'aside' }) {
  return (
    <Tag className={`rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 sm:p-5 ${className}`}>
      {children}
    </Tag>
  )
}

export function Skeleton({ className = 'h-4 w-full' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-slate-200 ${className}`} aria-hidden="true" />
}

export function PageSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-14 w-full" />)}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-2xl border-2 border-dashed border-slate-200 px-6 py-10 text-center">
      <p className="font-semibold text-navy-900">{title}</p>
      {children && <div className="mt-1 text-sm">{children}</div>}
    </div>
  )
}
