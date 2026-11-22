/** Phone-first frame for the customer and public pages (D-030): max ~720px, no agent chrome. */
import type { ReactNode } from 'react'

export function CustomerShell({ children, wide = false }: { children: ReactNode;
  wide?: boolean }) {
  return (
    <div className="min-h-dvh bg-slate-50">
      <header className="bg-navy-900 text-white">
        <div className={`mx-auto flex min-h-14 items-center gap-2 px-4 ${wide ? 'max-w-3xl'
          : 'max-w-[720px]'}`}>
          <span className="grid size-8 place-items-center rounded-xl bg-brand-600 text-sm
            font-bold" aria-hidden="true">A</span>
          <span className="font-semibold">Arvo Systems <span className="font-normal
            text-white/70">· Support</span></span>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-[720px] px-4 py-5 sm:py-8">{children}</main>
    </div>
  )
}
