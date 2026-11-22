/** Providers + routes (D-037). Declarative React Router; each page is a lazy chunk. */
import { QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense, useState } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router'
import { PageSkeleton } from '../components/ui/Card'
import { ToastProvider } from '../components/ui/Toast'
import { AgentLayout } from './AgentLayout'
import { ErrorBoundary } from './ErrorBoundary'
import { ErrorPolicy } from './ErrorPolicy'
import { RequireAgent, RequireLead, RootRedirect } from './guards'
import { createQueryClient } from './queryClient'

const LoginPage = lazy(() => import('../features/auth/pages/LoginPage'))
const TicketsPage = lazy(() => import('../features/tickets/pages/TicketsPage'))
const TicketPage = lazy(() => import('../features/ticket/pages/TicketPage'))
const LateReportPage = lazy(() => import('../features/reports/pages/LateReportPage'))
const HolidaysPage = lazy(() => import('../features/holidays/pages/HolidaysPage'))
const NewRequestPage = lazy(() => import('../features/public/pages/NewRequestPage'))
const CustomerTicketPage = lazy(() => import('../features/customer/pages/CustomerTicketPage'))
const NotFound = lazy(() => import('./NotFound'))

function Loading() {
  return <div className="mx-auto max-w-6xl p-4"><PageSkeleton /></div>
}

export default function App() {
  const [queryClient] = useState(createQueryClient)
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <BrowserRouter>
            <ErrorPolicy />
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route index element={<RootRedirect />} />
                <Route path="login" element={<LoginPage />} />
                <Route path="new" element={<NewRequestPage />} />
                <Route path="t" element={<CustomerTicketPage />} />
                <Route element={<RequireAgent />}>
                  <Route element={<AgentLayout />}>
                    <Route path="tickets" element={<TicketsPage />} />
                    <Route path="tickets/:id" element={<TicketPage />} />
                    <Route element={<RequireLead />}>
                      <Route path="reports/late" element={<LateReportPage />} />
                      <Route path="holidays" element={<HolidaysPage />} />
                    </Route>
                  </Route>
                </Route>
                <Route path="*" element={<NotFound />} />
              </Routes>
            </Suspense>
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
