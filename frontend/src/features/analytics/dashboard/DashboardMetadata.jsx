import { DASHBOARD_DESCRIPTION_MAX_LENGTH, DASHBOARD_TITLE_MAX_LENGTH } from './dashboardTypes'
import { validateDashboardMetadata } from './dashboardValidation'

export default function DashboardMetadata({ dashboard, onChange, onCreate }) {
  const validation = validateDashboardMetadata(dashboard?.title || '', dashboard?.description || '')
  const titleError = validation.errors.find((error) => error.toLowerCase().includes('title'))

  return (
    <section className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-base font-semibold text-white">Dashboard metadata</h3>
          <p className="mt-1 text-sm text-[var(--sf-text-muted)]">Create or preserve a dashboard title and optional description.</p>
        </div>
        <button
          type="button"
          onClick={onCreate}
          className="rounded-2xl bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600"
        >
          Create dashboard
        </button>
      </div>

      <div className="mt-4 grid gap-3">
        <label className="flex flex-col gap-2 text-sm text-[var(--sf-text-muted)]">
          <span className="font-semibold text-white">Dashboard title</span>
          <input
            aria-label="Dashboard title"
            value={dashboard?.title || ''}
            maxLength={DASHBOARD_TITLE_MAX_LENGTH}
            onChange={(event) => onChange({ title: event.target.value })}
            className="rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-white placeholder:text-[var(--sf-text-muted)] focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Required dashboard title"
          />
        </label>

        <label className="flex flex-col gap-2 text-sm text-[var(--sf-text-muted)]">
          <span className="font-semibold text-white">Description</span>
          <textarea
            aria-label="Dashboard description"
            value={dashboard?.description || ''}
            maxLength={DASHBOARD_DESCRIPTION_MAX_LENGTH}
            onChange={(event) => onChange({ description: event.target.value })}
            className="min-h-24 rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-white placeholder:text-[var(--sf-text-muted)] focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Optional dashboard description"
          />
        </label>

        {titleError && (
          <p className="text-sm text-rose-300">{titleError}</p>
        )}
      </div>
    </section>
  )
}
