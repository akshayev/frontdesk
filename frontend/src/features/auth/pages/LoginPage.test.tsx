/** D-048: after a submit attempt (success or failure) the password is hidden again. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { request } from '../../../api/client'
import LoginPage from './LoginPage'

vi.mock('../../../api/client', () => ({ request: vi.fn<typeof request>() }))
const mockedRequest = vi.mocked(request)

async function typeAndShow() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/login']}><LoginPage /></MemoryRouter>
    </QueryClientProvider>,
  )
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Email'), 'agent@example.test')
  const password = screen.getByLabelText('Password') as HTMLInputElement
  await user.type(password, 'typed-secret-1')
  await user.click(screen.getByRole('button', { name: 'Show password' }))
  expect(password.type).toBe('text')
  return { user, password }
}

beforeEach(() => { mockedRequest.mockReset() })

describe('LoginPage password toggle', () => {
  it('hides the password as soon as the form is submitted (request still pending)',
    async () => {
      mockedRequest.mockReturnValue(new Promise(() => {}) as never)
      const { user, password } = await typeAndShow()
      await user.click(screen.getByRole('button', { name: 'Sign in' }))
      expect(mockedRequest).toHaveBeenCalledTimes(1)
      expect(password.type).toBe('password')
      expect(screen.getByRole('button', { name: 'Show password' })
        .getAttribute('aria-pressed')).toBe('false')
    })

  it('stays hidden after a failed attempt, with the value kept', async () => {
    mockedRequest.mockRejectedValue(new Error('network down'))
    const { user, password } = await typeAndShow()
    await user.keyboard('{Enter}')
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(password.type).toBe('password')
    expect(password.value).toBe('typed-secret-1')
  })
})
