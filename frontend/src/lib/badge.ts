/** SLA badge text, tone and tooltip (UI-2, D-025, D-033). Colour is never the only signal:
 * every badge has text, and a title with the exact due time in IST. */
import type { Badge, BadgeState } from '../api/types'
import { formatIST, formatWorkingMinutes } from './format'

export function badgeText(badge: Pick<Badge, 'state' | 'minutes'>): string {
  switch (badge.state) {
    case 'late':
      return `Late ${formatWorkingMinutes(badge.minutes)}`
    case 'at_risk':
    case 'on_track':
      return `Due in ${formatWorkingMinutes(badge.minutes)}`
    case 'paused':
      return 'Paused'
    case 'met':
      return 'Met'
  }
}

/** Tailwind classes per state: late red, at risk amber, on track green, paused slate,
 * met emerald. */
export const BADGE_TONE: Record<BadgeState, string> = {
  late: 'bg-red-100 text-red-800 ring-red-300',
  at_risk: 'bg-amber-100 text-amber-900 ring-amber-300',
  on_track: 'bg-green-100 text-green-800 ring-green-300',
  paused: 'bg-slate-200 text-slate-700 ring-slate-300',
  met: 'bg-emerald-100 text-emerald-800 ring-emerald-300',
}

const TARGET_LABEL = { response: 'First response', resolution: 'Resolution' } as const

export function badgeTitle(badge: Pick<Badge, 'state' | 'target'>, dueAt: string | null): string {
  const target = TARGET_LABEL[badge.target]
  if (badge.state === 'paused') return `${target}: clock paused while waiting for the customer`
  if (!dueAt) return target
  const verb = badge.state === 'late' || badge.state === 'met' ? 'was due' : 'due'
  return `${target} ${verb} ${formatIST(dueAt)} (working hours 09:30–18:30 Mon–Fri)`
}

export function targetLabel(target: Badge['target']): string {
  return TARGET_LABEL[target]
}
