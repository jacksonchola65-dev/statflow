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
import { NavLink } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'

/** Roles that are allowed to see the "Import Data" link */
const IMPORT_ROLES = ['ADMIN', 'DATA_MANAGER']

/** Roles that are allowed to see the "User Management" link */
const ADMIN_ROLES = ['ADMIN']

export default function Topbar() {
  const { user, isAuthenticated, logout } = useAuth()

  const userRole = user?.role ?? null

  const canImport = isAuthenticated && IMPORT_ROLES.includes(userRole)
  const canManageUsers = isAuthenticated && ADMIN_ROLES.includes(userRole)

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
        <NavLink to="/dashboard" className={navLinkClass}>
          Dashboard
        </NavLink>
        <NavLink to="/analytics" className={navLinkClass}>
          Analytics
        </NavLink>
        <NavLink to="/decisions" className={navLinkClass}>
          Decisions
        </NavLink>

        {/* Import Data — hidden for VIEWER and ANALYST */}
        {canImport && (
          <NavLink to="/import" className={navLinkClass}>
            Import Data
          </NavLink>
        )}

        {/* User Management — ADMIN only */}
        {canManageUsers && (
          <NavLink to="/users" className={navLinkClass}>
            User Management
          </NavLink>
        )}
      </nav>

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
    </header>
  )
}
