/** Customer and public pages never redirect to the agent login (D-037 error policy). */
const PUBLIC_PREFIXES = ['/login', '/new', '/t']

export function isAgentPath(pathname: string): boolean {
  return !PUBLIC_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))
}
