/**
 * AuthContext.test.jsx
 *
 * Focused tests for AuthContext / AuthProvider.
 * Validates: REQ-13.6
 *
 * Covers:
 *  - Session restored by calling GET /auth/me (refreshSession) on mount
 *  - Logout clears user and csrfToken state
 *  - Initial loading state while /me is pending
 *  - Unauthenticated (401) startup leaves user null
 */
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'

// ---------------------------------------------------------------------------
// Mocks — hoisted before any imports that use them
// ---------------------------------------------------------------------------

vi.mock('../services/authApi', () => ({
  login: vi.fn(),
  getCurrentUser: vi.fn(),
  logout: vi.fn(),
}))

vi.mock('../services/api', () => ({
  default: {
    defaults: { withCredentials: true },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(),
  },
  registerCsrfTokenGetter: vi.fn(),
  registerUnauthenticatedHandler: vi.fn(),
}))

// ---------------------------------------------------------------------------
// Imports (after mocks)
// ---------------------------------------------------------------------------

import * as authApiMock from '../services/authApi'
import { AuthProvider, useAuth } from '../contexts/AuthContext'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MOCK_USER = { id: '1', email: 'alice@example.com', role: 'VIEWER' }
const MOCK_ME   = { user: MOCK_USER, csrf_token: 'csrf-xyz' }

/** Consumer component that exposes context values as text nodes */
function AuthDebug() {
  const { isLoading, isAuthenticated, user, csrfToken } = useAuth()
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="email">{user?.email ?? 'null'}</span>
      <span data-testid="csrf">{csrfToken ?? 'null'}</span>
    </div>
  )
}

/** Consumer that also exposes login / logout buttons */
function AuthActions() {
  const { user, csrfToken, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="email">{user?.email ?? 'null'}</span>
      <span data-testid="csrf">{csrfToken ?? 'null'}</span>
      <button onClick={() => login('alice@example.com', 'pw')}>Login</button>
      <button onClick={logout}>Logout</button>
    </div>
  )
}

/** Renders ui inside MemoryRouter + AuthProvider */
function renderWithAuth(ui, { initialEntries = ['/'] } = {}) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  // Default: startup returns 401
  const err401 = Object.assign(new Error('Unauthorized'), { response: { status: 401 } })
  authApiMock.getCurrentUser.mockRejectedValue(err401)
})

afterEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AuthContext — session restoration via GET /auth/me', () => {
  it('starts with isLoading=true before /auth/me resolves', async () => {
    // Keep getCurrentUser pending
    authApiMock.getCurrentUser.mockReturnValue(new Promise(() => {}))

    renderWithAuth(<AuthDebug />)

    // Immediately isLoading must be true
    expect(screen.getByTestId('loading').textContent).toBe('true')
  })

  it('calls getCurrentUser (GET /auth/me) once on mount', async () => {
    authApiMock.getCurrentUser.mockResolvedValue(MOCK_ME)

    renderWithAuth(<AuthDebug />)

    await waitFor(() =>
      expect(screen.getByTestId('loading').textContent).toBe('false')
    )

    // Should have been called exactly once — no retry loops
    expect(authApiMock.getCurrentUser).toHaveBeenCalledTimes(1)
  })

  it('sets user and csrfToken when /auth/me returns a valid session', async () => {
    authApiMock.getCurrentUser.mockResolvedValue(MOCK_ME)

    renderWithAuth(<AuthDebug />)

    await waitFor(() =>
      expect(screen.getByTestId('loading').textContent).toBe('false')
    )

    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(screen.getByTestId('email').textContent).toBe('alice@example.com')
    expect(screen.getByTestId('csrf').textContent).toBe('csrf-xyz')
  })

  it('leaves user null when /auth/me returns 401 (no session)', async () => {
    const err401 = Object.assign(new Error('Unauthorized'), { response: { status: 401 } })
    authApiMock.getCurrentUser.mockRejectedValue(err401)

    renderWithAuth(<AuthDebug />)

    await waitFor(() =>
      expect(screen.getByTestId('loading').textContent).toBe('false')
    )

    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    expect(screen.getByTestId('email').textContent).toBe('null')
    expect(screen.getByTestId('csrf').textContent).toBe('null')
  })

  it('does not store any token in localStorage — httpOnly cookie used instead', async () => {
    authApiMock.getCurrentUser.mockResolvedValue(MOCK_ME)

    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')

    renderWithAuth(<AuthDebug />)

    await waitFor(() =>
      expect(screen.getByTestId('loading').textContent).toBe('false')
    )

    // No JWT-related keys should be written to localStorage
    const jwtCalls = setItemSpy.mock.calls.filter(([key]) =>
      /jwt|token|access|auth/i.test(key)
    )
    expect(jwtCalls).toHaveLength(0)

    setItemSpy.mockRestore()
  })
})

describe('AuthContext — logout clears state', () => {
  it('clears user and csrfToken after logout', async () => {
    authApiMock.getCurrentUser.mockResolvedValue(MOCK_ME)
    authApiMock.logout.mockResolvedValue(undefined)

    renderWithAuth(<AuthActions />)

    // Wait until session is loaded
    await waitFor(() =>
      expect(screen.getByTestId('email').textContent).toBe('alice@example.com')
    )

    await userEvent.click(screen.getByText('Logout'))

    await waitFor(() =>
      expect(screen.getByTestId('email').textContent).toBe('null')
    )
    expect(screen.getByTestId('csrf').textContent).toBe('null')
  })

  it('calls the logout API when logout() is invoked', async () => {
    authApiMock.getCurrentUser.mockResolvedValue(MOCK_ME)
    authApiMock.logout.mockResolvedValue(undefined)

    renderWithAuth(<AuthActions />)

    await waitFor(() =>
      expect(screen.getByTestId('email').textContent).toBe('alice@example.com')
    )

    await userEvent.click(screen.getByText('Logout'))

    await waitFor(() => expect(authApiMock.logout).toHaveBeenCalledTimes(1))
  })

  it('propagates an error and preserves auth state when the logout API call fails', async () => {
    authApiMock.getCurrentUser.mockResolvedValue(MOCK_ME)
    // Simulate a non-401 logout failure (network error)
    authApiMock.logout.mockRejectedValue(new Error('Network Error'))

    // AuthProvider.logout is: await apiLogout(); clearAuth()
    // Since apiLogout re-throws non-401 errors, clearAuth is never reached.
    // The caller receives the error; auth state remains unchanged.
    let thrownError = null

    function AuthActionsWithCatch() {
      const { user, csrfToken, logout } = useAuth()
      const handleLogout = async () => {
        try { await logout() } catch (err) { thrownError = err }
      }
      return (
        <div>
          <span data-testid="email">{user?.email ?? 'null'}</span>
          <span data-testid="csrf">{csrfToken ?? 'null'}</span>
          <button onClick={handleLogout}>Logout</button>
        </div>
      )
    }

    render(
      <MemoryRouter>
        <AuthProvider><AuthActionsWithCatch /></AuthProvider>
      </MemoryRouter>
    )

    await waitFor(() =>
      expect(screen.getByTestId('email').textContent).toBe('alice@example.com')
    )

    await userEvent.click(screen.getByText('Logout'))

    // apiLogout threw — verify the error was propagated to the caller
    await waitFor(() => expect(thrownError).not.toBeNull())
    expect(thrownError.message).toBe('Network Error')

    // Auth state is preserved because clearAuth was never reached
    expect(screen.getByTestId('email').textContent).toBe('alice@example.com')
  })
})

describe('AuthContext — login updates state', () => {
  it('updates user and csrfToken after successful login', async () => {
    // Start unauthenticated
    const err401 = Object.assign(new Error('Unauthorized'), { response: { status: 401 } })
    authApiMock.getCurrentUser.mockRejectedValue(err401)
    authApiMock.login.mockResolvedValue(MOCK_ME)

    renderWithAuth(<AuthActions />)

    await waitFor(() =>
      expect(screen.getByTestId('email').textContent).toBe('null')
    )

    await userEvent.click(screen.getByText('Login'))

    await waitFor(() =>
      expect(screen.getByTestId('email').textContent).toBe('alice@example.com')
    )
    expect(screen.getByTestId('csrf').textContent).toBe('csrf-xyz')
  })
})
