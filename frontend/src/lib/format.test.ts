/** F-3 (D-039): working-minute formatting and the SLA badge text for every state (D-033). */
import { describe, expect, it } from 'vitest'
import { badgeText, badgeTitle } from './badge'
import { formatCalendarDate, formatIST, formatISTExact, formatWorkingMinutes } from './format'
import { customerStatusLabel } from './labels'

describe('formatWorkingMinutes', () => {
  it.each([
    [0, '0m'], [1, '1m'], [45, '45m'], [59, '59m'], [60, '1h'], [80, '1h 20m'], [120, '2h'],
    [190, '3h 10m'], [540, '9h'], [1620, '27h'], [-80, '1h 20m'],
  ])('%i → %s', (minutes, text) => {
    expect(formatWorkingMinutes(minutes)).toBe(text)
  })
})

describe('badgeText', () => {
  it.each([
    ['late', 80, 'Late 1h 20m'],
    ['at_risk', 45, 'Due in 45m'],
    ['on_track', 190, 'Due in 3h 10m'],
    ['paused', 300, 'Paused'],
    ['met', 0, 'Met'],
  ] as const)('%s %i → %s', (state, minutes, text) => {
    expect(badgeText({ state, minutes })).toBe(text)
  })

  it('title carries the exact due time in IST and says "working hours"', () => {
    const title = badgeTitle({ state: 'on_track', target: 'response' }, '2026-11-23T05:30:00Z')
    expect(title).toBe('First response due Mon, 23 Nov, 11:00 IST (working hours 09:30–18:30 Mon–Fri)')
    expect(badgeTitle({ state: 'late', target: 'resolution' }, '2026-11-23T05:30:00Z'))
      .toMatch(/^Resolution was due Mon, 23 Nov, 11:00 IST/)
    expect(badgeTitle({ state: 'paused', target: 'resolution' }, null)).toMatch(/paused/)
  })
})

describe('IST formatting', () => {
  it('formats in Asia/Kolkata regardless of the machine time zone', () => {
    expect(formatIST('2026-11-20T12:30:00Z')).toBe('Fri, 20 Nov, 18:00 IST')
    expect(formatISTExact('2026-11-20T12:30:05Z')).toBe('20 Nov 2026, 18:00:05 IST')
  })
})

describe('customerStatusLabel (D-033)', () => {
  it('maps every status, with the reopen deadline while reopen is possible', () => {
    const base = { can_reopen: false, reopen_until: null }
    expect(customerStatusLabel({ ...base, status: 'new' })).toMatch(/^Received/)
    expect(customerStatusLabel({ ...base, status: 'waiting_on_customer' }))
      .toBe('Waiting for your reply')
    expect(customerStatusLabel({ status: 'resolved', can_reopen: true,
      reopen_until: '2026-11-29T07:03:00Z' }))
      .toBe('Resolved — not fixed? You can reopen until Sun, 29 Nov, 12:33 IST')
    expect(customerStatusLabel({ ...base, status: 'resolved' })).toMatch(/^Closed/)
    expect(customerStatusLabel({ ...base, status: 'closed' })).toMatch(/^Closed/)
  })
})

describe('formatCalendarDate', () => {
  it('shows a holiday date without shifting the day', () => {
    expect(formatCalendarDate('2026-12-25')).toBe('Fri, 25 Dec 2026')
  })
})
