import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LoginScreen } from '../LoginScreen'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

beforeEach(() => {
  mockFetch.mockReset()
  // Default: auth status check returns passphrase is set
  mockFetch.mockResolvedValue(
    new Response(JSON.stringify({ has_owner: true, passphrase_set: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
})

describe('LoginScreen', () => {
  it('renders passphrase input and sign in button', () => {
    render(<LoginScreen />)
    expect(screen.getByPlaceholderText('Passphrase')).toBeInTheDocument()
    expect(screen.getByText('Sign In')).toBeInTheDocument()
  })

  it('disables sign in when passphrase is empty', () => {
    render(<LoginScreen />)
    const btn = screen.getByText('Sign In')
    expect(btn).toBeDisabled()
  })

  it('enables sign in when passphrase is typed', async () => {
    const user = userEvent.setup()
    render(<LoginScreen />)

    await user.type(screen.getByPlaceholderText('Passphrase'), 'secret123')
    expect(screen.getByText('Sign In')).not.toBeDisabled()
  })

  it('shows error on failed login', async () => {
    const user = userEvent.setup()

    // Override for the login attempt
    mockFetch
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ has_owner: true, passphrase_set: true }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Invalid passphrase' }), { status: 401 }),
      )

    render(<LoginScreen />)
    await user.type(screen.getByPlaceholderText('Passphrase'), 'wrong')
    await user.click(screen.getByText('Sign In'))

    expect(await screen.findByText('Invalid passphrase')).toBeInTheDocument()
  })

  it('shows forgot passphrase link', () => {
    render(<LoginScreen />)
    expect(screen.getByText('Forgot passphrase?')).toBeInTheDocument()
  })
})
