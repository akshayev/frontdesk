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

// One parts formatter; strings are composed by hand so the punctuation is the same in every
// browser and in Node (ICU versions differ on commas).
const partsFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})
const numberFmt = new Intl.NumberFormat('en-IN')

type Parts = Record<'weekday' | 'day' | 'month' | 'year' | 'hour' | 'minute' | 'second', string>

function parts(value: string | Date): Parts {
  const date = typeof value === 'string' ? new Date(value) : value
  const out: Parts = { weekday: '', day: '', month: '', year: '', hour: '', minute: '',
    second: '' }
  for (const part of partsFmt.formatToParts(date)) {
    if (part.type in out) out[part.type as keyof Parts] = part.value
  }
  return out
}

/** "Mon, 23 Nov, 11:00 IST" — lists, SLA panel. */
export function formatIST(value: string | Date): string {
  const p = parts(value)
  return `${p.weekday}, ${p.day} ${p.month}, ${p.hour}:${p.minute} IST`
}

/** "23 Nov 2026, 11:00:05 IST" — exact time (conversation, timeline, AUD-4). */
export function formatISTExact(value: string | Date): string {
  const p = parts(value)
  return `${p.day} ${p.month} ${p.year}, ${p.hour}:${p.minute}:${p.second} IST`
}

/** "Mon, 23 Nov 2026" — a calendar date in IST. */
export function formatISTDate(value: string | Date): string {
  const p = parts(value)
  return `${p.weekday}, ${p.day} ${p.month} ${p.year}`
}

/** A holiday's calendar date ("2026-12-25") without any time-zone shift. */
export function formatCalendarDate(isoDate: string): string {
  const [y, m, d] = isoDate.split('-').map(Number)
  // Noon UTC is the same calendar day in IST (UTC+05:30).
  return formatISTDate(new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1, 12)))
}

export function formatCount(value: number): string {
  return numberFmt.format(value)
}

/** "FD-1001" (ARCHITECTURE §3). */
export function ticketNumber(number: number): string {
  return `FD-${number}`
}
