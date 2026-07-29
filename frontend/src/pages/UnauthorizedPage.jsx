import { Link } from 'react-router-dom'

/**
 * UnauthorizedPage — shown when an authenticated user lacks the required role
 * to access a protected route.
 */
export default function UnauthorizedPage() {
  return (
    <main
      className="min-h-screen bg-[var(--sf-bg)] text-white flex flex-col items-center justify-center gap-6 px-6 text-center"
      aria-labelledby="unauthorized-heading"
    >
      <span className="text-7xl font-bold text-rose-400" aria-hidden="true">
        403
      </span>
      <h1
        id="unauthorized-heading"
        className="text-2xl font-semibold text-white"
      >
        Access denied
      </h1>
      <p className="text-[var(--sf-text-muted)] max-w-sm">
        You don&apos;t have permission to view this page. Contact an administrator
        if you believe this is a mistake.
      </p>
      <Link
        to="/dashboard"
        className="mt-2 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
      >
        ← Back to dashboard
      </Link>
    </main>
  )
}
