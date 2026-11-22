import type { ReactNode } from 'react'
import type { Badge as BadgeData, Priority, TicketStatus } from '../../api/types'
import { BADGE_TONE, badgeText, badgeTitle } from '../../lib/badge'
import { PRIORITY_LABEL, PRIORITY_TONE, STATUS_LABEL, STATUS_TONE } from '../../lib/labels'

export function Badge({ tone, title, children }: { tone: string; title?: string;
  children: ReactNode }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full
      px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${tone}`}>
      {children}
    </span>
  )
}

/** UI-2 SLA badge: colour + text + exact due time (IST) in the title (D-033). */
export function SlaBadge({ badge, dueAt }: { badge: Pick<BadgeData, 'state' | 'minutes' |
  'target'>; dueAt: string | null }) {
  const title = badgeTitle(badge, dueAt)
  return (
    <Badge tone={BADGE_TONE[badge.state]} title={title}>
      <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
      {badgeText(badge)}
      <span className="sr-only">. {title}</span>
    </Badge>
  )
}

export function StatusPill({ status }: { status: TicketStatus }) {
  return <Badge tone={`${STATUS_TONE[status]} ring-transparent`}>{STATUS_LABEL[status]}</Badge>
}

export function PriorityBadge({ priority }: { priority: Priority }) {
  return <Badge tone={PRIORITY_TONE[priority]}>{PRIORITY_LABEL[priority]}</Badge>
}
