import { useState, useCallback } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuth()
  const navigate  = useNavigate()
  const location  = useLocation()
  const from      = location.state?.from?.pathname || '/dashboard'

  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState(null)
  const [pending,  setPending]  = useState(false)

  // handleSubmit must be defined BEFORE any early return so hooks are
  // always called in the same order on every render.
  const handleSubmit = useCallback(async (e) => {
    e.preventDefault()
    if (pending) return

    setError(null)
    setPending(true)

    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch {
      // Generic error — never reveal whether the account exists or is inactive.
      // Credentials are NOT logged here.
      setError('Invalid email or password.')
    } finally {
      setPending(false)
    }
  }, [email, password, pending, login, navigate, from])

  // Redirect authenticated users away from /login.
  // Placed AFTER all hooks to avoid the "fewer hooks" React error.
  if (!isLoading && isAuthenticated) {
    return <Navigate to={from} replace />
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--sf-bg)] px-4">
      <div className="w-full max-w-sm">
        {/* Logo / branding */}
        <div className="text-center mb-8">
          <h1
            className="text-3xl font-bold text-white tracking-tight"
            style={{ fontFamily: 'var(--sf-font-family)' }}
          >
            StatFlow
          </h1>
          <p className="mt-1 text-sm text-[var(--sf-text-muted)]">
            Sign in to your account
          </p>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-white/10 bg-[var(--sf-surface)] p-8 shadow-xl">
          <form onSubmit={handleSubmit} noValidate aria-label="Sign in form">
            {/* Email */}
            <div className="mb-4">
              <label
                htmlFor="email"
                className="block mb-1.5 text-sm font-medium text-[var(--sf-text)]"
              >
                Email address
              </label>
              <input
                id="email"
                type="email"
                name="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={pending}
                className="w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2.5 text-sm text-white placeholder-[var(--sf-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--sf-focus-ring)] focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                placeholder="you@example.com"
              />
            </div>

            {/* Password */}
            <div className="mb-5">
              <label
                htmlFor="password"
                className="block mb-1.5 text-sm font-medium text-[var(--sf-text)]"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                name="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={pending}
                className="w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2.5 text-sm text-white placeholder-[var(--sf-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--sf-focus-ring)] focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                placeholder="••••••••"
              />
            </div>

            {/* Error message — accessible to screen readers */}
            {error && (
              <div
                role="alert"
                aria-live="assertive"
                className="mb-4 rounded-lg bg-rose-900/30 border border-rose-500/40 px-4 py-3 text-sm text-rose-300"
              >
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={pending}
              aria-busy={pending}
              className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 active:bg-indigo-700 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--sf-bg)] disabled:bg-indigo-600/40 disabled:text-white/50 disabled:cursor-not-allowed"
            >
              {pending ? (
                <>
                  <svg
                    aria-hidden="true"
                    className="animate-spin w-4 h-4"
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
                  Signing in…
                </>
              ) : (
                'Sign in'
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
