import { useEffect } from 'react'

/** Document title per screen (screen readers announce it on navigation). */
export function usePageTitle(title: string, suffix = 'Frontdesk'): void {
  useEffect(() => {
    document.title = `${title} · ${suffix}`
  }, [title, suffix])
}
