import { Link } from 'react-router'
import { buttonClass } from '../components/ui/buttonClass'

export default function NotFound() {
  return (
    <main className="mx-auto grid min-h-dvh max-w-md place-items-center p-6 text-center">
      <div>
        <p className="text-sm font-semibold text-brand-600">404</p>
        <h1 className="mt-2 text-2xl font-semibold">This page does not exist</h1>
        <p className="mt-2">Check the address, or go back to the start.</p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link to="/" className={buttonClass('primary')}>Go to Frontdesk</Link>
          <Link to="/new" className={buttonClass('secondary')}>Submit a problem</Link>
        </div>
      </div>
    </main>
  )
}
