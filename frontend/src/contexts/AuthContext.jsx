import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { getCurrentUser, login as apiLogin, logout as apiLogout } from '../services/authApi'
import { registerCsrfTokenGetter, registerUnauthenticatedHandler } from '../services/api'

export const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser]           = useState(null)
  const [csrfToken, setCsrfToken] = useState(null)
  const [isLoading, setIsLoading] = useState(true)   // true until /me resolves

  // Derived state
  const isAuthenticated = !!user

  // ── Centralized clear ──────────────────────────────────────────────────
  const clearAuth = useCallback(() => {
    setUser(null)
    setCsrfToken(null)
  }, [])

  // ── Register CSRF getter so api.js interceptor can read the token ──────
  // Use a ref to avoid stale closure in the registered callback
  const csrfRef = useRef(csrfToken)
  useEffect(() => { csrfRef.current = csrfToken }, [csrfToken])

  useEffect(() => {
    registerCsrfTokenGetter(() => csrfRef.current)
    registerUnauthenticatedHandler(clearAuth)
  }, [clearAuth])

  // ── Startup: restore session via /auth/me ──────────────────────────────
  const refreshSession = useCallback(async () => {
    try {
      const { user: me, csrf_token } = await getCurrentUser()
      setUser(me)
      setCsrfToken(csrf_token)
    } catch {
      // 401 = not authenticated — clear state silently
      clearAuth()
    } finally {
      setIsLoading(false)
    }
  }, [clearAuth])

  useEffect(() => {
    refreshSession()
    // Only run once on mount — no dependencies that would cause a loop
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── login ──────────────────────────────────────────────────────────────
  const login = useCallback(async (email, password) => {
    const { user: me, csrf_token } = await apiLogin(email, password)
    setUser(me)
    setCsrfToken(csrf_token)
    return me
  }, [])

  // ── logout ─────────────────────────────────────────────────────────────
  const logout = useCallback(async () => {
    await apiLogout()
    clearAuth()
  }, [clearAuth])

  return (
    <AuthContext.Provider value={{
      user,
      csrfToken,
      isAuthenticated,
      isLoading,
      login,
      logout,
      refreshSession,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
