/** Formatting helpers: working minutes, IST dates (AUD-4: exact to the second for customers). */

const TZ = 'Asia/Kolkata'

/** Working minutes as "1h 20m", "45m", "2h" (D-033). Negative values use the absolute value. */
export function formatWorkingMinutes(minutes: number): string {
  const total = Math.round(Math.abs(minutes))
  const hours = Math.floor(total / 60)
  const rest = total % 60
  if (hours === 0) return `${rest}m`
  if (rest === 0) return `${hours}h`
  return `${hours}h ${rest}m`
}

const shortFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit',
  minute: '2-digit', hourCycle: 'h23',
})
const exactFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ, day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit',
  minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})
const dateFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
})
const numberFmt = new Intl.NumberFormat('en-IN')

function toDate(value: string | Date): Date {
  return typeof value === 'string' ? new Date(value) : value
}

/** "Mon, 23 Nov, 11:00 IST" — lists, SLA panel, timeline. */
export function formatIST(value: string | Date): string {
  return `${shortFmt.format(toDate(value))} IST`
}

/** "23 Nov 2026, 11:00:05 IST" — exact time (customer thread, AUD-4). */
export function formatISTExact(value: string | Date): string {
  return `${exactFmt.format(toDate(value))} IST`
}

/** "Mon, 23 Nov 2026" — a calendar date in IST. */
export function formatISTDate(value: string | Date): string {
  return dateFmt.format(toDate(value))
}

/** A holiday's calendar date ("2026-12-25") without any time-zone shift. */
export function formatCalendarDate(isoDate: string): string {
  const [y, m, d] = isoDate.split('-').map(Number)
  return dateFmt.format(new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1, 12)))
}

export function formatCount(value: number): string {
  return numberFmt.format(value)
}

/** "FD-1001" (ARCHITECTURE §3). */
export function ticketNumber(number: number): string {
  return `FD-${number}`
}
