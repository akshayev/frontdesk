/** F-2 (D-039): the API contract — standard error JSON → ApiError, non-JSON bodies, the CSRF
 * header on non-GET only, and the customer token header. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { request } from './client'
import { ApiError, NETWORK_ERROR } from './errors'

type Call = { url: string; init: RequestInit }

function stubFetch(response: () => Response | Promise<Response>): Call[] {
  const calls: Call[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init })
    return response()
  }))
  return calls
}

function headersOf(call: Call | undefined): Record<string, string> {
  return (call?.init.headers ?? {}) as Record<string, string>
}

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    if (error instanceof ApiError) return error
    throw error
  }
  throw new Error('expected the request to fail')
}

afterEach(() => vi.unstubAllGlobals())

describe('request()', () => {
  it('parses the standard error JSON into ApiError, keeping extra fields', async () => {
    stubFetch(() => new Response(JSON.stringify({
      error: 'already_claimed', message: 'Arjun has already taken this ticket.',
      request_id: 'req-123', owner: { id: 'u1', name: 'Arjun' },
    }), { status: 409, headers: { 'Content-Type': 'application/json' } }))

    const error = await caught(request('post', '/api/agent/tickets/{ticket_id}/claim', {
      path: { ticket_id: 't1' } }))
    expect(error.status).toBe(409)
    expect(error.code).toBe('already_claimed')
    expect(error.message).toBe('Arjun has already taken this ticket.')
    expect(error.requestId).toBe('req-123')
    expect(error.extra).toEqual({ owner: { id: 'u1', name: 'Arjun' } })
  })

  it('handles a non-JSON error body (proxy HTML page) with the X-Request-ID header', async () => {
    stubFetch(() => new Response('<html>Bad gateway</html>', {
      status: 502, headers: { 'X-Request-ID': 'hdr-9' } }))

    const error = await caught(request('get', '/api/auth/me'))
    expect(error.status).toBe(502)
    expect(error.code).toBe('internal_error')
    expect(error.requestId).toBe('hdr-9')
    expect(error.message).toMatch(/went wrong/i)
    expect(error.extra).toEqual({})
  })

  it('handles an empty error body', async () => {
    stubFetch(() => new Response(null, { status: 429 }))
    const error = await caught(request('get', '/api/agent/tickets'))
    expect([error.status, error.code]).toEqual([429, 'rate_limited'])
  })

  it('turns a network failure into a network_error ApiError (status 0)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    const error = await caught(request('get', '/api/auth/me'))
    expect([error.status, error.code]).toEqual([0, NETWORK_ERROR])
  })

  it('sends X-Requested-With on non-GET only, same-origin credentials, JSON body', async () => {
    const calls = stubFetch(() => Response.json([]))
    await request('get', '/api/agent/tickets', { query: { view: 'late' } })
    await request('post', '/api/agent/tickets/{ticket_id}/notes', {
      path: { ticket_id: 'a b' }, body: { body: 'hi', expected_version: 3 } })
    await request('delete', '/api/lead/holidays/{day}', { path: { day: '2026-12-25' } })

    const [get, post, del] = calls
    expect(get?.url).toBe('/api/agent/tickets?view=late')
    expect(get?.init.method).toBe('GET')
    expect(headersOf(get)['X-Requested-With']).toBeUndefined()
    expect(get?.init.credentials).toBe('same-origin')

    expect(post?.url).toBe('/api/agent/tickets/a%20b/notes')
    expect(headersOf(post)['X-Requested-With']).toBe('frontdesk')
    expect(headersOf(post)['Content-Type']).toBe('application/json')
    expect(JSON.parse(String(post?.init.body))).toEqual({ body: 'hi', expected_version: 3 })

    expect(del?.init.method).toBe('DELETE')
    expect(headersOf(del)['X-Requested-With']).toBe('frontdesk')
  })

  it('sends the customer token as X-Ticket-Token, never in the URL', async () => {
    const calls = stubFetch(() => Response.json({}))
    await request('get', '/api/customer/ticket', { token: 'tok_SECRET' })
    expect(headersOf(calls[0])['X-Ticket-Token']).toBe('tok_SECRET')
    expect(calls[0]?.url).toBe('/api/customer/ticket')
  })

  it('returns undefined for 204 and the parsed JSON otherwise', async () => {
    stubFetch(() => new Response(null, { status: 204 }))
    await expect(request('post', '/api/auth/logout')).resolves.toBeUndefined()
    stubFetch(() => Response.json({ ok: true, checked: 5, first_bad_id: null }))
    await expect(request('get', '/api/lead/audit/verify')).resolves.toEqual(
      { ok: true, checked: 5, first_bad_id: null })
  })
})
