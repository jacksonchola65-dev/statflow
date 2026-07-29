export default function DashboardToolbar({
  dashboard,
  onTogglePreview,
  onReset,
  onCreate,
  onSave,
  onLoad,
  onDelete,
  selectedDashboardId,
  savedDashboards = [],
  onSelectDashboard,
  saving = false,
  loadingSaved = false,
  deleteDisabled = true,
}) {
  const dirtyMessage = dashboard?.dirty ? 'You have unsaved dashboard changes.' : null
  const isPersisted = Boolean(dashboard?.id && !String(dashboard.id).startsWith('dashboard-'))

  return (
    <section className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            aria-label="Create dashboard"
            onClick={onCreate}
            className="rounded-2xl bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-600"
          >
            Create dashboard
          </button>
          <button
            type="button"
            aria-label="Save dashboard"
            onClick={onSave}
            disabled={saving}
            className="rounded-2xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saving ? 'Saving...' : 'Save dashboard'}
          </button>
          <button
            type="button"
            aria-label="Delete saved dashboard"
            onClick={onDelete}
            disabled={deleteDisabled || !isPersisted}
            className="rounded-2xl border border-rose-400/40 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-100 hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Delete saved
          </button>
          <button
            type="button"
            aria-label="Toggle preview mode"
            onClick={onTogglePreview}
            className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10"
          >
            {dashboard?.previewMode ? 'Return to edit' : 'Preview mode'}
          </button>
          <button
            type="button"
            aria-label="Reset dashboard"
            onClick={onReset}
            className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10"
          >
            Reset
          </button>
        </div>

        <div className="flex flex-col gap-2 lg:items-end">
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-sm text-[var(--sf-text-muted)]" htmlFor="saved-dashboard-select">
              Saved dashboards
            </label>
            <select
              id="saved-dashboard-select"
              aria-label="Saved dashboards"
              value={selectedDashboardId || ''}
              onChange={(event) => onSelectDashboard(event.target.value)}
              className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-sm text-white"
            >
              <option value="">Select a saved dashboard</option>
              {savedDashboards.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title || 'Untitled dashboard'}
                </option>
              ))}
            </select>
            <button
              type="button"
              aria-label="Load selected dashboard"
              onClick={onLoad}
              disabled={!selectedDashboardId || loadingSaved}
              className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loadingSaved ? 'Loading...' : 'Load selected'}
            </button>
          </div>
          <div className="text-sm text-[var(--sf-text-muted)]">
            {dirtyMessage || 'Dashboard is currently in sync with the current draft.'}
          </div>
        </div>
      </div>
    </section>
  )
}
