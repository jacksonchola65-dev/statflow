/**
 * LoginPage.test.jsx
 *
 * Focused tests for the LoginPage component.
 * Validates: REQ-13.6
 *
 * Covers:
 *  - Renders email + password form
 *  - Calls login() on submit
 *  - Shows error message on failed login
 *  - Redirects to /dashboard (or intended page) on success
 */
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'

// ---------------------------------------------------------------------------
// Mocks — hoisted before any module-level imports that use them
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
import { AuthProvider } from '../contexts/AuthContext'
import LoginPage from '../pages/LoginPage'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MOCK_USER = { id: '1', email: 'user@example.com', role: 'VIEWER' }
const MOCK_ME   = { user: MOCK_USER, csrf_token: 'csrf-abc' }

/** Renders LoginPage inside MemoryRouter + AuthProvider */
function renderLoginPage({ initialEntries = ['/login'] } = {}) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AuthProvider>
        <Routes>
          <Route path="/login"     element={<LoginPage />} />
          <Route path="/dashboard" element={<div>Dashboard</div>} />
          <Route path="/reports"   element={<div>Reports</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  // Default: unauthenticated startup
  const err401 = Object.assign(new Error('Unauthorized'), { response: { status: 401 } })
  authApiMock.getCurrentUser.mockRejectedValue(err401)
})

afterEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LoginPage — rendering', () => {
  it('renders the email and password fields', async () => {
    renderLoginPage()

    // Wait for loading state to finish
    await waitFor(() =>
      expect(screen.queryByLabelText('Loading session')).not.toBeInTheDocument()
    )

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('renders the Sign in submit button', async () => {
    renderLoginPage()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
    )
  })

  it('does not show an error initially', async () => {
    renderLoginPage()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
    )

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('LoginPage — form submission calls login()', () => {
  it('calls login() with the entered credentials on submit', async () => {
    authApiMock.login.mockResolvedValue(MOCK_ME)

    renderLoginPage()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
    )

    await userEvent.type(screen.getByLabelText(/email address/i), 'user@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'secret123')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() =>
      expect(authApiMock.login).toHaveBeenCalledWith('user@example.com', 'secret123')
    )
  })

  it('disables the submit button while the login request is pending', async () => {
    // Keep the login promise pending indefinitely
    authApiMock.login.mockReturnValue(new Promise(() => {}))

    renderLoginPage()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
    )

    await userEvent.type(screen.getByLabelText(/email address/i), 'user@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled()
    )
  })
})

describe('LoginPage — error message on failure', () => {
  it('shows "Invalid email or password." when login fails with 401', async () => {
    authApiMock.login.mockRejectedValue(
      Object.assign(new Error('Unauthorized'), { response: { status: 401 } })
    )

    renderLoginPage()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
    )

    await userEvent.type(screen.getByLabelText(/email address/i), 'bad@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'wrongpass')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toBeInTheDocument()
    )
    expect(screen.getByRole('alert').textContent).toMatch(/invalid email or password/i)
  })

  it('re-enables the submit button after a failed login', async () => {
    authApiMock.login.mockRejectedValue(
      Object.assign(new Error('Unauthorized'), { response: { status: 401 } })
    )

    renderLoginPage()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
    )

    await userEvent.type(screen.getByLabelText(/email address/i), 'bad@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'wrongpass')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    // After failure the button should go back to "Sign in" and be enabled
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).not.toBeDisabled()
    )
  })
})

describe('LoginPage — redirect on success', () => {
  it('redirects to /dashboard after successful login (no intended page)', async () => {
    authApiMock.getCurrentUser.mockResolvedValue({ user: null, csrf_token: null })
    authApiMock.login.mockResolvedValue(MOCK_ME)

    renderLoginPage({ initialEntries: ['/login'] })

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
    )

    await userEvent.type(screen.getByLabelText(/email address/i), 'user@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() =>
      expect(screen.getByText('Dashboard')).toBeInTheDocument()
    )
  })

  it('redirects to the originally intended page after successful login', async () => {
    authApiMock.getCurrentUser.mockResolvedValue({ user: null, csrf_token: null })
    authApiMock.login.mockResolvedValue(MOCK_ME)

    // Simulate arriving at /login with state.from = /reports
    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/login', state: { from: { pathname: '/reports' } } }]}
      >
        <AuthProvider>
          <Routes>
            <Route path="/login"   element={<LoginPage />} />
            <Route path="/reports" element={<div>Reports</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    )

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
    )

    await userEvent.type(screen.getByLabelText(/email address/i), 'user@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() =>
      expect(screen.getByText('Reports')).toBeInTheDocument()
    )
  })

  it('redirects an already-authenticated user away from /login', async () => {
    authApiMock.getCurrentUser.mockResolvedValue(MOCK_ME)

    renderLoginPage({ initialEntries: ['/login'] })

    await waitFor(() =>
      expect(screen.getByText('Dashboard')).toBeInTheDocument()
    )
    expect(screen.queryByLabelText(/email address/i)).not.toBeInTheDocument()
  })
})
