/**
 * The one fetch wrapper (D-037). Same origin, cookie session for agents, X-Ticket-Token for
 * customers, X-Requested-With: frontdesk on every non-GET (CSRF, SECURITY §1). Typed from the
 * generated OpenAPI schema: path, method, path params, query, body and response all come from
 * src/api/schema.d.ts. Non-2xx → ApiError.
 */
import { ApiError, NETWORK_ERROR, parseError } from './errors'
import type { paths } from './schema'

export type HttpMethod = 'get' | 'post' | 'patch' | 'delete'
export type ApiPath = keyof paths

type Operation<P extends ApiPath, M extends HttpMethod> = NonNullable<paths[P][M]>

/** The methods a path actually defines. */
export type MethodOf<P extends ApiPath> = {
  [M in HttpMethod]: [NonNullable<paths[P][M]>] extends [never] ? never : M
}[HttpMethod]

type SuccessOf<O> = O extends { responses: infer R }
  ? R extends { 200: infer S } ? S
    : R extends { 201: infer S } ? S
      : R extends { 204: infer S } ? S
        : never
  : never

type JsonOf<S> = S extends { content: { 'application/json': infer T } } ? T : undefined

export type ResponseOf<P extends ApiPath, M extends MethodOf<P>> =
  JsonOf<SuccessOf<Operation<P, M>>>

type BodyOf<O> = O extends { requestBody: { content: { 'application/json': infer B } } }
  ? B : never
type PathParamsOf<O> = O extends { parameters: { path: infer PP } } ? PP : never
type QueryOf<O> = O extends { parameters: { query?: infer Q } } ? Q : never

type PathOption<O> = [PathParamsOf<O>] extends [never]
  ? { path?: never } : { path: PathParamsOf<O> }
type BodyOption<O> = [BodyOf<O>] extends [never] ? { body?: never } : { body: BodyOf<O> }
type QueryOption<O> = [QueryOf<O>] extends [undefined]
  ? { query?: never } : { query?: NonNullable<QueryOf<O>> }

export type RequestOptions<O> = PathOption<O> & BodyOption<O> & QueryOption<O> & {
  /** Customer secret (D-038): sent as X-Ticket-Token, never in the URL. */
  token?: string
  signal?: AbortSignal
}

type Args<O> = object extends RequestOptions<O>
  ? [options?: RequestOptions<O>]
  : [options: RequestOptions<O>]

type Primitive = string | number | boolean

function buildUrl(template: string, pathParams: object | undefined, query: object | undefined):
  string {
  const params = (pathParams ?? {}) as Record<string, Primitive>
  const filled = template.replace(/\{(\w+)\}/g, (_, name: string) => {
    const value = params[name]
    if (value === undefined) throw new Error(`Missing path parameter ${name}`)
    return encodeURIComponent(String(value))
  })
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries((query ?? {}) as Record<string, unknown>)) {
    if (value !== undefined && value !== null) search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `${filled}?${qs}` : filled
}

/** Call the API. Resolves with the typed success body (undefined for 204). */
export async function request<P extends ApiPath, M extends MethodOf<P>>(
  method: M,
  path: P,
  ...[options]: Args<Operation<P, M>>
): Promise<ResponseOf<P, M>> {
  const opts = (options ?? {}) as { path?: object; query?: object; body?: unknown;
    token?: string; signal?: AbortSignal }
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'get') headers['X-Requested-With'] = 'frontdesk'
  if (opts.token) headers['X-Ticket-Token'] = opts.token

  let response: Response
  try {
    response = await fetch(buildUrl(path, opts.path, opts.query), {
      method: method.toUpperCase(),
      credentials: 'same-origin',
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      signal: opts.signal,
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError(0, NETWORK_ERROR, 'Could not reach Frontdesk. Check your connection.',
      null)
  }

  const text = await response.text()
  if (!response.ok) {
    throw parseError(response.status, text, response.headers.get('X-Request-ID'))
  }
  if (response.status === 204 || text === '') return undefined as ResponseOf<P, M>
  try {
    return JSON.parse(text) as ResponseOf<P, M>
  } catch {
    throw new ApiError(response.status, 'invalid_response', 'The server sent an unreadable reply.',
      response.headers.get('X-Request-ID'))
  }
}
