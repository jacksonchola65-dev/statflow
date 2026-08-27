/**
 * Topbar — sticky global header.
 *
 * Contains:
 *  - "StatFlow" wordmark (logo)
 *  - Subtitle: "Zambia Development Intelligence Platform"
 *  - Nav links: Dashboard, Import Data (ADMIN/DATA_MANAGER), User Management (ADMIN)
 *  - Logged-in user's display name
 *  - Logout button
 *
 * Uses CSS custom properties from src/index.css tokens.
 */
import { useEffect, useRef, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'

/** Roles that are allowed to see the "Import Data" link */
const IMPORT_ROLES = ['ADMIN', 'DATA_MANAGER']

/** Roles that are allowed to see the "User Management" link */
const ADMIN_ROLES = ['ADMIN']

export default function Topbar() {
  const { user, isAuthenticated, logout } = useAuth()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const menuButtonRef = useRef(null)

  const userRole = user?.role ?? null

  const canImport = isAuthenticated && IMPORT_ROLES.includes(userRole)
  const canManageUsers = isAuthenticated && ADMIN_ROLES.includes(userRole)

  const primaryRoutes = [
    { to: '/dashboard', label: 'Dashboard' },
    { to: '/analytics', label: 'Analytics' },
    { to: '/decisions', label: 'Decisions' },
    ...(canImport ? [{ to: '/import', label: 'Import Data' }] : []),
    ...(canManageUsers ? [{ to: '/users', label: 'User Management' }] : []),
  ]

  useEffect(() => {
    if (!mobileMenuOpen) return undefined

    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setMobileMenuOpen(false)
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', closeOnEscape)

    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [mobileMenuOpen])

  useEffect(() => {
    if (!mobileMenuOpen) menuButtonRef.current?.focus()
  }, [mobileMenuOpen])

  const closeMobileMenu = () => setMobileMenuOpen(false)

  /** Display name: prefer full_name, fall back to email */
  const displayName = user?.full_name?.trim() || user?.email || null

  const navLinkClass = ({ isActive }) =>
    [
      'text-[12px] font-medium uppercase tracking-[var(--sf-tracking-wide)]',
      'px-3 py-1.5 rounded-lg',
      'transition-colors duration-150',
      'focus-visible:outline-none focus-visible:ring-2',
      'focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-1',
      'focus-visible:ring-offset-[var(--sf-bg)]',
      isActive
        ? 'bg-indigo-500/15 text-indigo-400'
        : 'text-[var(--sf-text-subtle)] hover:text-[var(--sf-text)] hover:bg-white/5',
    ].join(' ')

  return (
    <header
      className="
        sticky top-0 z-50
        border-b border-[var(--sf-border)]
        bg-slate-900/80 backdrop-blur-md
        px-4 sm:px-6 lg:px-8
        py-3
        flex items-center gap-4
      "
      role="banner"
    >
      {/* ---- Logo + subtitle ---- */}
      <div className="flex flex-col min-w-0 flex-shrink-0">
        <h1
          className="
            text-[22px] font-extrabold leading-none tracking-tight text-white
            [font-family:var(--sf-font-family)]
          "
        >
          Stat
          <span className="text-indigo-400">Flow</span>
        </h1>

        <p
          className="
            hidden sm:block
            mt-0.5
            text-[11px] font-medium uppercase tracking-[var(--sf-tracking-widest)]
            text-[var(--sf-text-subtle)]
            whitespace-nowrap
          "
          aria-label="Zambia Development Intelligence Platform"
        >
          Zambia Development Intelligence Platform
        </p>

        {/* Mobile: shorter subtitle to avoid overflow */}
        <p
          className="
            block sm:hidden
            mt-0.5
            text-[10px] font-medium uppercase tracking-wide
            text-[var(--sf-text-subtle)]
          "
          aria-hidden="true"
        >
          Development Intelligence
        </p>
      </div>

      {/* ---- Navigation links (desktop) ---- */}
      <nav
        className="hidden sm:flex items-center gap-1 ml-4"
        aria-label="Main navigation"
      >
        {primaryRoutes.map((route) => (
          <NavLink key={route.to} to={route.to} className={navLinkClass}>
            {route.label}
          </NavLink>
        ))}
      </nav>

      {/* Mobile navigation trigger and drawer */}
      <button
        ref={menuButtonRef}
        type="button"
        className="ml-auto inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg border border-white/10 text-[var(--sf-text)] hover:bg-white/5 sm:hidden"
        aria-label={mobileMenuOpen ? 'Close main navigation' : 'Open main navigation'}
        aria-controls="mobile-main-navigation"
        aria-expanded={mobileMenuOpen}
        onClick={() => setMobileMenuOpen(true)}
      >
        <span className="flex w-5 flex-col gap-1" aria-hidden="true">
          <span className="h-0.5 w-full bg-current" />
          <span className="h-0.5 w-full bg-current" />
          <span className="h-0.5 w-full bg-current" />
        </span>
      </button>

      {/* ---- Right-side: user info + logout ---- */}
      <div className="ml-auto flex items-center gap-3 flex-shrink-0">
        {/* Logged-in user display */}
        {isAuthenticated && displayName && (
          <span
            className="
              hidden sm:block
              text-[12px] font-medium
              text-[var(--sf-text-subtle)]
              max-w-[160px] truncate
            "
            title={displayName}
            aria-label={`Logged in as ${displayName}`}
          >
            {displayName}
          </span>
        )}

        {/* Logout button */}
        {isAuthenticated && (
          <button
            type="button"
            onClick={logout}
            className="
              text-[12px] font-medium uppercase tracking-[var(--sf-tracking-wide)]
              px-3 py-1.5 rounded-lg
              transition-colors duration-150
              text-[var(--sf-text-subtle)] hover:text-red-400 hover:bg-red-500/10
              focus-visible:outline-none focus-visible:ring-2
              focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-1
              focus-visible:ring-offset-[var(--sf-bg)]
            "
            aria-label="Log out"
          >
            Log out
          </button>
        )}
      </div>

      {mobileMenuOpen && (
        <div className="fixed inset-0 z-[60] sm:hidden" role="presentation">
          <button
            type="button"
            className="absolute inset-0 h-full w-full bg-black/60"
            aria-label="Close main navigation"
            onClick={closeMobileMenu}
          />
          <aside
            id="mobile-main-navigation"
            className="absolute right-0 top-0 flex h-full w-[min(86vw,22rem)] flex-col border-l border-white/10 bg-slate-900 p-5 shadow-2xl"
            aria-label="Mobile main navigation"
          >
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <p className="text-xs font-bold uppercase tracking-[var(--sf-tracking-widest)] text-slate-400">Navigate</p>
              <button
                type="button"
                className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-2xl text-slate-300 hover:bg-white/5"
                aria-label="Close main navigation"
                onClick={closeMobileMenu}
              >
                <span aria-hidden="true">x</span>
              </button>
            </div>
            <nav className="flex flex-col gap-2 pt-5" aria-label="Mobile main navigation links">
              {primaryRoutes.map((route) => (
                <NavLink
                  key={route.to}
                  to={route.to}
                  end={route.to === '/dashboard'}
                  onClick={closeMobileMenu}
                  className={({ isActive }) => [
                    'min-h-11 rounded-lg px-4 py-3 text-sm font-semibold transition-colors',
                    isActive
                      ? 'bg-indigo-500/15 text-indigo-300'
                      : 'text-slate-300 hover:bg-white/5 hover:text-white',
                  ].join(' ')}
                >
                  {route.label}
                </NavLink>
              ))}
            </nav>
          </aside>
        </div>
      )}
    </header>
  )
}
