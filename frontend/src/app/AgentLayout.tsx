/** Agent/lead shell: navy top bar, nav (lead items for the lead), user + Logout. On phones the
 * nav collapses behind a menu button (D-030). */
import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { Button } from '../components/ui/Button'
import { CloseIcon, MenuIcon } from '../components/ui/Icon'
import { useLogout, useMe } from '../features/auth/queries'

type NavItem = { to: string; label: string; lead?: boolean }
const NAV: readonly NavItem[] = [
  { to: '/tickets', label: 'Tickets' },
  { to: '/reports/late', label: 'Late report', lead: true },
  { to: '/holidays', label: 'Holidays', lead: true },
]

function navClass({ isActive }: { isActive: boolean }): string {
  return `flex min-h-11 items-center rounded-full px-4 text-sm font-semibold transition-colors ${
    isActive ? 'bg-white/15 text-white' : 'text-white/80 hover:bg-white/10 hover:text-white'}`
}

export function AgentLayout() {
  const me = useMe()
  const logout = useLogout()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [lastPath, setLastPath] = useState(location.pathname)
  if (lastPath !== location.pathname) {
    // Close the phone menu after navigating.
    setLastPath(location.pathname)
    setMenuOpen(false)
  }

  const agent = me.data
  const items = NAV.filter((item) => !item.lead || agent?.role === 'lead')

  async function onLogout() {
    await logout.mutateAsync().catch(() => undefined)
    navigate('/login', { replace: true })
  }

  const user = agent && (
    <div className="flex items-center gap-3">
      <div className="min-w-0 text-right leading-tight">
        <p className="truncate text-sm font-semibold text-white">{agent.name}</p>
        <p className="text-xs text-white/70">{agent.role === 'lead' ? 'Support lead' : 'Agent'}</p>
      </div>
      <Button variant="onDark" size="sm" onClick={onLogout} busy={logout.isPending}>
        Log out
      </Button>
    </div>
  )

  return (
    <div className="min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2
        focus:top-2 focus:z-50 focus:rounded-full focus:bg-white focus:px-4 focus:py-2">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 bg-navy-900 text-white shadow">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-2">
          <NavLink to="/tickets" className="flex min-h-11 items-center gap-2 font-semibold">
            <span className="grid size-8 place-items-center rounded-xl bg-brand-600 text-sm
              font-bold" aria-hidden="true">F</span>
            <span>Frontdesk <span className="font-normal text-white/70">· Arvo Systems</span></span>
          </NavLink>
          <nav aria-label="Main" className="hidden flex-1 items-center gap-1 md:flex">
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} className={navClass}>{item.label}</NavLink>
            ))}
          </nav>
          <div className="ml-auto hidden md:block">{user}</div>
          <button type="button" className="ml-auto grid size-11 place-items-center rounded-full
            hover:bg-white/10 md:hidden" aria-expanded={menuOpen} aria-controls="mobile-nav"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            onClick={() => setMenuOpen((open) => !open)}>
            {menuOpen ? <CloseIcon /> : <MenuIcon />}
          </button>
        </div>
        {menuOpen && (
          <div id="mobile-nav" className="border-t border-white/10 px-4 pb-4 md:hidden">
            <nav aria-label="Main" className="flex flex-col gap-1 py-3">
              {items.map((item) => (
                <NavLink key={item.to} to={item.to} className={navClass}>{item.label}</NavLink>
              ))}
            </nav>
            <div className="flex justify-end border-t border-white/10 pt-3">{user}</div>
          </div>
        )}
      </header>
      <main id="main" className="mx-auto max-w-7xl px-4 py-5 md:py-8">
        <Outlet />
      </main>
    </div>
  )
}
