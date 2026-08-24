import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import DashboardPage from '../pages/DashboardPage'
import AnalyticsPage from '../pages/AnalyticsPage'
import DecisionWorkspacePage from '../pages/DecisionWorkspacePage'
import ImportPage from '../pages/ImportPage'
import LoginPage from '../pages/LoginPage'
import NotFoundPage from '../pages/NotFoundPage'
import UnauthorizedPage from '../pages/UnauthorizedPage'
import ProtectedRoute from '../components/auth/ProtectedRoute'

/**
 * Root redirect: send authenticated users to /dashboard, unauthenticated to /login.
 * We check isLoading so we don't flash a redirect before the session is restored.
 */
function RootRedirect() {
  const { isAuthenticated, isLoading } = useAuth()

  // While session is loading, render nothing — ProtectedRoute handles the spinner
  if (isLoading) return null

  return isAuthenticated
    ? <Navigate to="/dashboard" replace />
    : <Navigate to="/login" replace />
}

export default function AppRouter() {
  return (
    <Routes>
      {/* ---- Public ---- */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/unauthorized" element={<UnauthorizedPage />} />

      {/* ---- Root redirect ---- */}
      <Route path="/" element={<RootRedirect />} />

      {/* ---- Protected: any authenticated user ---- */}
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/analytics"
        element={
          <ProtectedRoute>
            <AnalyticsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/decisions"
        element={
          <ProtectedRoute>
            <DecisionWorkspacePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/decisions/business-location"
        element={
          <ProtectedRoute>
            <DecisionWorkspacePage />
          </ProtectedRoute>
        }
      />

      {/* ---- Protected: ADMIN or DATA_MANAGER only ---- */}
      <Route
        path="/import"
        element={
          <ProtectedRoute allowedRoles={['ADMIN', 'DATA_MANAGER']}>
            <ImportPage />
          </ProtectedRoute>
        }
      />

      {/* ---- Protected: ADMIN only ---- */}
      <Route
        path="/users"
        element={
          <ProtectedRoute allowedRoles={['ADMIN']}>
            {/* UsersPage will be implemented in a future task */}
            <div className="flex h-screen items-center justify-center text-[var(--sf-text-subtle)]">
              User Management (coming soon)
            </div>
          </ProtectedRoute>
        }
      />

      {/* ---- 404 ---- */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
