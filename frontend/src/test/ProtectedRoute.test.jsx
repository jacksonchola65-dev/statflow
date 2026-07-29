/**
 * ProtectedRoute.test.jsx
 *
 * Focused tests for the ProtectedRoute component.
 * Validates: REQ-13.6
 *
 * Covers:
 *  - Unauthenticated user is redirected to /login
 *  - Loading state shows spinner (no redirect)
 *  - Authenticated user without role restriction passes through
 *  - Authenticated user with insufficient role sees UnauthorizedPage
 *  - allowedRoles prop works correctly
 */
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
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
import { AuthProvider } from '../contexts/AuthContext'
import ProtectedRoute from '../components/auth/ProtectedRoute'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const VIEWER_USER  = { id: '1', email: 'viewer@example.com',  role: 'VIEWER'  }
const ADMIN_USER   = { id: '2', email: 'admin@example.com',   role: 'ADMIN'   }
const ANALYST_USER = { id: '3', email: 'analyst@example.com', role: 'ANALYST' }

/** Renders a ProtectedRoute inside a full MemoryRouter + AuthProvider scaffold */
function renderProtectedRoute({
  initialEntries = ['/dashboard'],
  allowedRoles,
} = {}) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AuthProvider>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute allowedRoles={allowedRoles}>
                <div>Secret Content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/login"        element={<div>Login Page</div>} />
          <Route path="/unauthorized" element={<div>Unauthorized Page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ProtectedRoute — unauthenticated', () => {
  it('redirects to /login when the user is not authenticated', async () => {
    const err401 = Object.assign(new Error('Unauthorized'), { response: { status: 401 } })
    authApiMock.getCurrentUser.mockRejectedValue(err401)

    renderProtectedRoute()

    await waitFor(() =>
      expect(screen.getByText('Login Page')).toBeInTheDocument()
    )
    expect(screen.queryByText('Secret Content')).not.toBeInTheDocument()
  })

  it('preserves the originally requested path in location.state.from', async () => {
    const err401 = Object.assign(new Error('Unauthorized'), { response: { status: 401 } })
    authApiMock.getCurrentUser.mockRejectedValue(err401)

    let capturedState = null

    function LoginCapture() {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const { useLocation } = require('react-router-dom')
      const location = useLocation()
      capturedState = location.state
      return <div>Login Page</div>
    }

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <AuthProvider>
          <Routes>
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <div>Secret Content</div>
                </ProtectedRoute>
              }
            />
            <Route path="/login" element={<LoginCapture />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    )

    await waitFor(() =>
      expect(screen.getByText('Login Page')).toBeInTheDocument()
    )
    expect(capturedState?.from?.pathname).toBe('/dashboard')
  })
})

describe('ProtectedRoute — loading state', () => {
  it('shows a spinner while session is loading', async () => {
    // Keep getCurrentUser pending — isLoading stays true
    authApiMock.getCurrentUser.mockReturnValue(new Promise(() => {}))

    renderProtectedRoute()

    // Spinner should appear; no redirect to /login
    await waitFor(() =>
      expect(screen.getByRole('status')).toBeInTheDocument()
    )
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
    expect(screen.queryByText('Secret Content')).not.toBeInTheDocument()
  })

  it('does not redirect while session is still loading', async () => {
    authApiMock.getCurrentUser.mockReturnValue(new Promise(() => {}))

    renderProtectedRoute()

    // Give it a moment — it should still NOT be on /login
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
  })
})

describe('ProtectedRoute — authorized user passes through', () => {
  it('renders children when the user is authenticated (no allowedRoles)', async () => {
    authApiMock.getCurrentUser.mockResolvedValue({
      user: VIEWER_USER,
      csrf_token: 'tok',
    })

    renderProtectedRoute()

    await waitFor(() =>
      expect(screen.getByText('Secret Content')).toBeInTheDocument()
    )
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
  })

  it('renders children when user role is in allowedRoles', async () => {
    authApiMock.getCurrentUser.mockResolvedValue({
      user: ADMIN_USER,
      csrf_token: 'tok',
    })

    renderProtectedRoute({ allowedRoles: ['ADMIN', 'DATA_MANAGER'] })

    await waitFor(() =>
      expect(screen.getByText('Secret Content')).toBeInTheDocument()
    )
  })
})

describe('ProtectedRoute — allowedRoles restriction', () => {
  it('shows UnauthorizedPage when user role is not in allowedRoles', async () => {
    authApiMock.getCurrentUser.mockResolvedValue({
      user: ANALYST_USER,
      csrf_token: 'tok',
    })

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <AuthProvider>
          <Routes>
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute allowedRoles={['ADMIN']}>
                  <div>Secret Content</div>
                </ProtectedRoute>
              }
            />
            <Route path="/login" element={<div>Login Page</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    )

    // UnauthorizedPage renders an "Access denied" heading
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /access denied/i })).toBeInTheDocument()
    )
    expect(screen.queryByText('Secret Content')).not.toBeInTheDocument()
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
  })

  it('renders children when user role matches one of multiple allowedRoles', async () => {
    authApiMock.getCurrentUser.mockResolvedValue({
      user: { ...VIEWER_USER, role: 'DATA_MANAGER' },
      csrf_token: 'tok',
    })

    renderProtectedRoute({ allowedRoles: ['ADMIN', 'DATA_MANAGER'] })

    await waitFor(() =>
      expect(screen.getByText('Secret Content')).toBeInTheDocument()
    )
  })
})
