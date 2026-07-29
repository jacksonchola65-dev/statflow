export default function VisualizationToolbar({
  currentView,
  onViewChange,
  chartType,
  onChartTypeChange,
  supportedChartTypes,
  recommendation,
  disabled,
}) {
  const viewOptions = [
    { value: 'table', label: 'Table' },
    { value: 'visualization', label: 'Visualization' },
  ]

  const chartOptionLabels = {
    kpi: 'KPI cards',
    bar: 'Bar chart',
    line: 'Line chart',
    area: 'Area chart',
    pie: 'Pie chart',
  }

  return (
    <div className="space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div role="tablist" aria-label="Result view" className="flex flex-wrap gap-2">
          {viewOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={currentView === option.value}
              onClick={() => onViewChange(option.value)}
              disabled={disabled}
              className={[
                'rounded-full px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sf-focus-ring)]',
                currentView === option.value
                  ? 'bg-indigo-500 text-white'
                  : 'bg-slate-900 text-[var(--sf-text-muted)] hover:bg-white/10',
              ].join(' ')}
            >
              {option.label}
            </button>
          ))}
        </div>

        <label className="flex items-center gap-2 text-sm text-[var(--sf-text-muted)]">
          <span className="font-semibold text-white">Chart type</span>
          <select
            aria-label="Chart type"
            value={chartType}
            onChange={(event) => onChartTypeChange(event.target.value)}
            className="rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {supportedChartTypes.map((type) => (
              <option key={type} value={type}>
                {chartOptionLabels[type] || type}
              </option>
            ))}
          </select>
        </label>
      </div>

      {recommendation && (
        <p className="text-sm text-[var(--sf-text-muted)]">{recommendation}</p>
      )}
    </div>
  )
}
