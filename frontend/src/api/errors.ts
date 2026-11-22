/** The standard error JSON {error, message, request_id, ...extra} as a typed error (D-037). */

export type ErrorExtra = Record<string, unknown>

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly extra: ErrorExtra

  constructor(status: number, code: string, message: string, requestId: string | null,
    extra: ErrorExtra = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
    this.extra = extra
  }
}

export const NETWORK_ERROR = 'network_error'

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

export function hasCode(error: unknown, ...codes: string[]): error is ApiError {
  return isApiError(error) && codes.includes(error.code)
}

/** 4xx errors are answers, not glitches: never retried (D-037). */
export function isClientError(error: unknown): boolean {
  return isApiError(error) && error.status >= 400 && error.status < 500
}

/** already_claimed carries {owner: {id, name}}. */
export function ownerName(error: ApiError): string {
  const owner = error.extra.owner
  if (typeof owner === 'object' && owner !== null && 'name' in owner) {
    const name = (owner as { name: unknown }).name
    if (typeof name === 'string' && name) return name
  }
  return 'another agent'
}

function fallbackCode(status: number): string {
  if (status === 401) return 'unauthorized'
  if (status === 403) return 'forbidden'
  if (status === 404) return 'not_found'
  if (status === 429) return 'rate_limited'
  if (status >= 500) return 'internal_error'
  return 'http_error'
}

function fallbackMessage(status: number): string {
  if (status === 429) return 'Too many requests — wait a minute.'
  if (status >= 500) return 'Something went wrong on our side.'
  return `The request failed (HTTP ${status}).`
}

/** Build an ApiError from a non-2xx response body (already read as text). */
export function parseError(status: number, bodyText: string, headerRequestId: string | null):
  ApiError {
  let parsed: unknown = null
  try {
    parsed = bodyText ? JSON.parse(bodyText) : null
  } catch {
    parsed = null
  }
  if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
    const { error, message, request_id: requestId, ...extra } = parsed as Record<string, unknown>
    return new ApiError(
      status,
      typeof error === 'string' ? error : fallbackCode(status),
      typeof message === 'string' && message ? message : fallbackMessage(status),
      typeof requestId === 'string' ? requestId : headerRequestId,
      extra,
    )
  }
  return new ApiError(status, fallbackCode(status), fallbackMessage(status), headerRequestId)
}
