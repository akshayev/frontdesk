/** Agent login (SECURITY §2). The server's generic message is shown as-is (D-029). */
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { isApiError } from '../../../api/errors'
import { Button } from '../../../components/ui/Button'
import { TextField } from '../../../components/ui/Field'
import { AlertIcon } from '../../../components/ui/Icon'
import { safeNext, useLogin } from '../queries'

export default function LoginPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const login = useLogin()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    login.mutate({ email: email.trim(), password }, {
      onSuccess: () => navigate(safeNext(params.get('next')), { replace: true }),
    })
  }

  const error = login.error
  const message = !error ? null
    : isApiError(error) && error.status === 429 ? 'Too many attempts — wait a minute and try again.'
      : isApiError(error) ? error.message : 'Could not sign in.'

  return (
    <div className="grid min-h-dvh bg-navy-900 md:grid-cols-2">
      <div className="hidden flex-col justify-between p-10 text-white md:flex">
        <p className="font-semibold">Frontdesk <span className="text-white/60">· Arvo Systems</span></p>
        <div>
          <h1 className="max-w-md text-4xl font-semibold leading-tight text-white">
            Every customer answered on time.
          </h1>
          <p className="mt-4 max-w-md text-white/75">
            Shared support inbox with working-hours SLAs, internal notes that never leak, and a
            history you can prove.
          </p>
        </div>
        <p className="text-sm text-white/50">Support team sign-in</p>
      </div>
      <main className="flex items-center justify-center bg-slate-50 p-4 md:rounded-l-[2rem]">
        <div className="w-full max-w-sm">
          <p className="mb-6 font-semibold text-navy-900 md:hidden">
            Frontdesk <span className="font-normal text-ink">· Arvo Systems</span>
          </p>
          <h2 className="text-2xl font-semibold">Sign in</h2>
          <p className="mt-1 text-sm">For Arvo support agents and the support lead.</p>
          <form className="mt-6 space-y-4" onSubmit={onSubmit} noValidate>
            <TextField label="Email" type="email" autoComplete="username" required
              value={email} onChange={(e) => setEmail(e.target.value)} inputMode="email" />
            <TextField label="Password" type="password" autoComplete="current-password" required
              value={password} onChange={(e) => setPassword(e.target.value)} />
            {message && (
              <p role="alert" className="flex items-start gap-2 rounded-xl bg-red-50 p-3 text-sm
                text-red-900 ring-1 ring-red-200">
                <AlertIcon className="mt-0.5 size-4 shrink-0" />{message}
              </p>
            )}
            <Button type="submit" size="lg" className="w-full" busy={login.isPending}
              disabled={!email || !password}>
              Sign in
            </Button>
          </form>
          <div className="mt-8 space-y-2 text-sm">
            <p>
              Customer?{' '}
              <Link to="/new" className="font-semibold text-brand-700 underline underline-offset-2">
                Submit a problem
              </Link>
            </p>
            <p className="text-slate-600">Demo accounts are listed in the README.</p>
          </div>
        </div>
      </main>
    </div>
  )
}
