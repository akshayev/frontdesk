/** Last-resort render error boundary: a friendly message instead of a blank page. */
import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { buttonClass } from '../components/ui/buttonClass'

type State = { failed: boolean }

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // No remote logging (no third-party origin); keep it visible in the console for support.
    console.error('Frontdesk render error', error, info.componentStack)
  }

  override render(): ReactNode {
    if (!this.state.failed) return this.props.children
    return (
      <div className="mx-auto max-w-xl p-6">
        <div role="alert" className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h1 className="text-xl font-semibold">Something went wrong on this page</h1>
          <p className="mt-2">Reload the page to try again. Nothing you sent has been lost.</p>
          <a href={window.location.href} className={buttonClass('primary', 'md', 'mt-4')}>
            Reload
          </a>
        </div>
      </div>
    )
  }
}
