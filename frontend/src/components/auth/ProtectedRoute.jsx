import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import UnauthorizedPage from '../../pages/UnauthorizedPage'

/**
 * ProtectedRoute — wraps content that requires authentication.
 *
 * - While the session is loading, shows a spinner (no redirect yet).
 * - When unauthenticated, redirects to /login, preserving the attempted path
 *   in `location.state.from` so LoginPage can redirect back after login.
 * - When authenticated, renders children.
 * - Optionally accepts `allowedRoles` to restrict access by user role.
 *
 * @param {{ children: React.ReactNode, allowedRoles?: string[] }} props
 */
export default function ProtectedRoute({ children, allowedRoles }) {
  const { isAuthenticated, isLoading, user } = useAuth()
  const location = useLocation()

  // While AuthContext is still loading, show a spinner.
  // IMPORTANT: Do NOT redirect here — we don't know if the user is logged in yet.
  if (isLoading) {
    return (
      <div
        className="flex h-screen items-center justify-center"
        aria-label="Loading session"
        role="status"
      >
        <svg
          aria-hidden="true"
          className="animate-spin w-8 h-8 text-indigo-400"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
          />
        </svg>
      </div>
    )
  }

  // Not authenticated — redirect to /login, preserving the requested location
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // Role check (optional)
  if (allowedRoles && user && !allowedRoles.includes(user.role)) {
    return <UnauthorizedPage />
  }

  return children
}
