/** F-1 (D-039): the INC-0304 surface. Note mode is unmistakable, reply mode says it goes to the
 * customer, and switching modes never sends text to the wrong endpoint. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { request } from '../../../api/client'
import { Composer } from './Composer'

vi.mock('../../../api/client', () => ({ request: vi.fn<typeof request>() }))
const mockedRequest = vi.mocked(request)

const TICKET = 'a3b1c2d4-0000-4000-8000-000000000001'

function setup(props: Partial<Parameters<typeof Composer>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Composer ticketId={TICKET} version={7} customerName="Neha Agarwal" canReply canWait
        {...props} />
    </QueryClientProvider>,
  )
  return userEvent.setup()
}

function calledPaths(): string[] {
  return mockedRequest.mock.calls.map((call) => String(call[1]))
}

beforeEach(() => {
  mockedRequest.mockReset()
  mockedRequest.mockResolvedValue({ version: 8 } as never)
})

describe('Composer', () => {
  it('note mode shows the banner, the lock icon and "Save internal note"', async () => {
    const user = setup()
    await user.click(screen.getByRole('button', { name: /add internal note/i }))

    expect(screen.getByText('Internal note — only your team can see this')).toBeTruthy()
    expect(screen.getByRole('img', { name: 'Private' })).toBeTruthy()
    expect(screen.getByRole('button', { name: /save internal note/i })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /send to customer/i })).toBeNull()
    expect(screen.queryByLabelText(/wait for the customer/i)).toBeNull()
  })

  it('reply mode shows "Send to customer" and the wait option, no note banner', async () => {
    const user = setup()
    await user.click(screen.getByRole('button', { name: /reply to customer/i }))

    expect(screen.getByRole('button', { name: /send to customer/i })).toBeTruthy()
    expect(screen.getByLabelText("and wait for the customer's answer")).toBeTruthy()
    expect(screen.getByText(/the customer will see this message/i)).toBeTruthy()
    expect(screen.queryByText(/only your team can see this/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /save internal note/i })).toBeNull()
  })

  it('a note typed and then a switch to reply never sends the note to the customer',
    async () => {
      const user = setup()
      await user.click(screen.getByRole('button', { name: /add internal note/i }))
      await user.type(screen.getByLabelText('Internal note'), 'SECRET root cause')

      await user.click(screen.getByRole('button', { name: /reply to customer/i }))
      const reply = screen.getByLabelText('Reply to Neha Agarwal') as HTMLTextAreaElement
      expect(reply.value).toBe('') // separate drafts: the note text did not follow
      await user.type(reply, 'We are on it')
      await user.click(screen.getByRole('button', { name: /send to customer/i }))

      expect(calledPaths()).toEqual(['/api/agent/tickets/{ticket_id}/replies'])
      expect(mockedRequest).toHaveBeenCalledWith('post', '/api/agent/tickets/{ticket_id}/replies', {
        path: { ticket_id: TICKET },
        body: { body: 'We are on it', expected_version: 7, wait_for_customer: false },
      })
      expect(JSON.stringify(mockedRequest.mock.calls)).not.toContain('SECRET')
    })

  it('a reply typed and then a switch to note saves only the note, to /notes', async () => {
    const user = setup()
    await user.click(screen.getByRole('button', { name: /reply to customer/i }))
    await user.type(screen.getByLabelText('Reply to Neha Agarwal'), 'Draft for customer')
    await user.click(screen.getByRole('button', { name: /add internal note/i }))
    await user.type(screen.getByLabelText('Internal note'), 'Escalated to eng')
    await user.click(screen.getByRole('button', { name: /save internal note/i }))

    expect(calledPaths()).toEqual(['/api/agent/tickets/{ticket_id}/notes'])
    expect(mockedRequest).toHaveBeenCalledWith('post', '/api/agent/tickets/{ticket_id}/notes', {
      path: { ticket_id: TICKET },
      body: { body: 'Escalated to eng', expected_version: 7 },
    })
  })

  it('"and wait" is sent only when ticked', async () => {
    const user = setup()
    await user.click(screen.getByRole('button', { name: /reply to customer/i }))
    await user.type(screen.getByLabelText('Reply to Neha Agarwal'), 'Which browser?')
    await user.click(screen.getByLabelText("and wait for the customer's answer"))
    await user.click(screen.getByRole('button', { name: /send to customer/i }))

    expect(mockedRequest.mock.calls[0]?.[2]).toMatchObject({
      body: { wait_for_customer: true } })
  })

  it('without the reply action only the note button exists; R does nothing, N opens notes',
    async () => {
      const user = setup({ canReply: false, canWait: false })
      expect(screen.queryByRole('button', { name: /reply to customer/i })).toBeNull()
      await user.keyboard('r')
      expect(screen.queryByRole('button', { name: /send to customer/i })).toBeNull()
      await user.keyboard('n')
      expect(screen.getByRole('button', { name: /save internal note/i })).toBeTruthy()
    })

  it('shortcuts are ignored while typing in a text field', async () => {
    const user = setup()
    await user.click(screen.getByRole('button', { name: /add internal note/i }))
    await user.type(screen.getByLabelText('Internal note'), 'run the report')
    // The "r" letters above must not have switched to reply mode.
    expect(screen.getByRole('button', { name: /save internal note/i })).toBeTruthy()
  })
})
