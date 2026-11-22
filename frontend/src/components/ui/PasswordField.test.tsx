/** D-048: the show/hide toggle changes only how the value is displayed and never submits. */
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { PasswordField } from './Field'

function Form({ onSubmit }: { onSubmit: () => void }) {
  const [value, setValue] = useState('')
  const [visible, setVisible] = useState(false)
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit() }}>
      <PasswordField label="Password" autoComplete="current-password" value={value}
        onChange={(e) => setValue(e.target.value)} visible={visible}
        onVisibleChange={setVisible} />
    </form>
  )
}

function setup() {
  const onSubmit = vi.fn<() => void>()
  render(<Form onSubmit={onSubmit} />)
  return { onSubmit, user: userEvent.setup(), input: screen.getByLabelText('Password') as
    HTMLInputElement }
}

describe('PasswordField', () => {
  it('toggles type, aria-label and aria-pressed; value and autocomplete unchanged', async () => {
    const { user, input } = setup()
    await user.type(input, 'abc123')
    expect(input.type).toBe('password')

    await user.click(screen.getByRole('button', { name: 'Show password' }))
    const hide = screen.getByRole('button', { name: 'Hide password' })
    expect(input.type).toBe('text')
    expect(hide.getAttribute('aria-pressed')).toBe('true')
    expect(input.value).toBe('abc123')
    expect(input.getAttribute('autocomplete')).toBe('current-password')
    expect(input.getAttribute('spellcheck')).toBe('false')

    await user.click(hide)
    const show = screen.getByRole('button', { name: 'Show password' })
    expect(input.type).toBe('password')
    expect(show.getAttribute('aria-pressed')).toBe('false')
    expect(input.value).toBe('abc123')
  })

  it('the toggle is type="button" and never submits the form (click, Enter, Space)',
    async () => {
      const { user, onSubmit } = setup()
      const toggle = screen.getByRole('button', { name: 'Show password' })
      expect(toggle.getAttribute('type')).toBe('button')

      const input = screen.getByLabelText('Password')
      await user.click(toggle)
      expect(input.getAttribute('type')).toBe('text')
      toggle.focus()
      await user.keyboard('{Enter}')
      expect(input.getAttribute('type')).toBe('password')
      await user.keyboard(' ')
      expect(input.getAttribute('type')).toBe('text')
      expect(onSubmit).not.toHaveBeenCalled()
    })

  it('a mouse click keeps the focus in the input', async () => {
    const { user, input } = setup()
    await user.click(input)
    await user.click(screen.getByRole('button', { name: 'Show password' }))
    expect(document.activeElement).toBe(input)
  })

  it('is hidden again when the page is left (pagehide)', async () => {
    const { user, input } = setup()
    await user.click(screen.getByRole('button', { name: 'Show password' }))
    expect(input.type).toBe('text')
    fireEvent(window, new Event('pagehide'))
    expect(input.type).toBe('password')
  })
})
