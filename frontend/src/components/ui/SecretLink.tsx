/** The secret customer link, shown ONCE (IN-1, IN-2, RO-4) with Copy and a warning (D-033). */
import { useState } from 'react'
import { CheckIcon, CopyIcon, ShieldIcon } from './Icon'
import { copyText } from '../../lib/clipboard'
import { Button } from './Button'

export function CopyButton({ text, label = 'Copy link', variant = 'primary' }: {
  text: string; label?: string; variant?: 'primary' | 'secondary' }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  return (
    <>
      <Button variant={variant} onClick={async () => setState(await copyText(text) ? 'copied'
        : 'failed')}>
        {state === 'copied' ? <CheckIcon className="size-4" /> : <CopyIcon className="size-4" />}
        {state === 'copied' ? 'Copied' : label}
      </Button>
      <span className="sr-only" aria-live="polite">
        {state === 'copied' ? 'Link copied to the clipboard.' : ''}
        {state === 'failed' ? 'Could not copy. Select the link and copy it by hand.' : ''}
      </span>
    </>
  )
}

export function SecretLink({ link, audience }: { link: string; audience: 'customer' | 'agent' }) {
  return (
    <div className="rounded-2xl bg-brand-50 p-4 ring-1 ring-brand-200">
      <label className="block text-sm font-semibold text-navy-900" htmlFor="secret-link">
        {audience === 'customer' ? 'Your private link' : 'Customer link'}
      </label>
      <input id="secret-link" readOnly value={link} onFocus={(e) => e.currentTarget.select()}
        className="mt-2 block w-full rounded-xl border-0 bg-white px-3 py-2.5 font-mono text-sm
          text-navy-900 ring-1 ring-inset ring-brand-200" />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <CopyButton text={link} />
      </div>
      <p className="mt-3 flex items-start gap-2 text-sm text-navy-900">
        <ShieldIcon className="mt-0.5 size-4 shrink-0 text-brand-600" />
        {audience === 'customer'
          ? "Save this link — it's your private key to this request. Don't share it."
          : 'Share only with this customer. It is shown once and cannot be shown again.'}
      </p>
    </div>
  )
}
