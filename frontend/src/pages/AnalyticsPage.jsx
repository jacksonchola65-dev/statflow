import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AppShell from '../components/layout/AppShell'
import ErrorState from '../components/common/ErrorState'
import LoadingState from '../components/common/LoadingState'
import {
  AnalyticsVisualization,
  VisualizationToolbar,
  getVisualizationCompatibility,
} from '../features/analytics/visualization'
import { DashboardWorkspace } from '../features/analytics/dashboard'
import {
  listAnalyticsDatasets,
  getDatasetDetails,
  getDatasetSchema,
  getDatasetDimensions,
  getDatasetMeasures,
  getDatasetPreview,
  getDatasetStatistics,
  executeAnalyticsQuery,
} from '../services/analyticsApi'

const PAGE_SIZE = 10
const PREVIEW_LIMIT = 10

const AGGREGATION_LABELS = {
  COUNT: 'Count',
  COUNT_DISTINCT: 'Count distinct',
  SUM: 'Sum',
  AVERAGE: 'Average',
  MINIMUM: 'Minimum',
  MAXIMUM: 'Maximum',
}

const TAB_KEYS = ['schema', 'dimensions', 'measures', 'preview', 'query']

function toLocaleDate(value) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  return isNaN(date.getTime())
    ? 'Unknown'
    : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function formatNumber(value) {
  return typeof value === 'number' ? value.toLocaleString() : String(value)
}

function safeCellValue(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'True' : 'False'
  return String(value)
}

function isRequestCancelled(error) {
  return (
    error?.name === 'CanceledError' ||
    error?.code === 'ERR_CANCELED' ||
    String(error?.message).toLowerCase().includes('canceled')
  )
}

function DatasetItem({ item, isSelected, onSelect }) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(item.ingestion_job_id)}
        aria-current={isSelected ? 'true' : undefined}
        className={[
          'w-full text-left rounded-2xl border px-4 py-4 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--sf-bg)]',
          isSelected
            ? 'border-indigo-500/60 bg-indigo-500/10'
            : 'border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/10',
        ].join(' ')}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white truncate">{item.dataset_name}</p>
            <p className="mt-1 text-xs text-[var(--sf-text-muted)] truncate">
              {item.source_name || 'Unknown source'}
            </p>
          </div>
          <span
            className={[
              'rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ',
              isSelected ? 'bg-indigo-600 text-white' : 'bg-white/5 text-[var(--sf-text-muted)]',
            ].join(' ')}
          >
            {item.row_count.toLocaleString()} rows
          </span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 text-[13px] text-[var(--sf-text-muted)]">
          <div>
            <span className="block text-white/80">Columns</span>
            <span>{item.column_count.toLocaleString()}</span>
          </div>
          <div>
            <span className="block text-white/80">Completed</span>
            <span>{toLocaleDate(item.completed_at || item.created_at)}</span>
          </div>
        </div>
      </button>
    </li>
  )
}

function DatasetBrowser({
  datasets,
  total,
  limit,
  offset,
  hasMore,
  loading,
  error,
  selectedDatasetId,
  searchTerm,
  onSearch,
  onPrevious,
  onNext,
  onRetry,
  onSelect,
}) {
  const filtered = useMemo(() => {
    const query = searchTerm.trim().toLowerCase()
    if (!query) return datasets
    return datasets.filter((item) =>
      item.dataset_name.toLowerCase().includes(query) ||
      (item.source_name || '').toLowerCase().includes(query)
    )
  }, [datasets, searchTerm])

  return (
    <aside className="flex flex-col gap-4">
      <div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">Dataset browser</h2>
            <p className="mt-1 text-sm text-[var(--sf-text-muted)]">
              Browse analytics-ready datasets and select one to inspect.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--sf-text-muted)]">
            <span>{total.toLocaleString()} available</span>
            <span aria-hidden="true">·</span>
            <span>Page size: {limit}</span>
          </div>
        </div>

        <div className="mt-4">
          <label htmlFor="dataset-search" className="sr-only">
            Search datasets
          </label>
          <input
            id="dataset-search"
            type="search"
            value={searchTerm}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Search visible datasets"
            className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-white placeholder:text-[var(--sf-text-muted)] focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          />
          <p className="mt-2 text-xs text-[var(--sf-text-muted)]">
            Search filters the currently loaded page only.
          </p>
        </div>
      </div>

      {loading && <LoadingState message="Loading datasets…" />}

      {error && !loading && (
        <ErrorState message={error} onRetry={onRetry} />
      )}

      {!loading && !error && filtered.length === 0 && (
        <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-sm text-[var(--sf-text-muted)]">
          No matching datasets on this page.
        </div>
      )}

      {!loading && !error && filtered.length > 0 && (
        <ul className="space-y-3">
          {filtered.map((item) => (
            <DatasetItem
              key={item.ingestion_job_id}
              item={item}
              isSelected={item.ingestion_job_id === selectedDatasetId}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}

      <div className="mt-auto flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onPrevious}
          disabled={offset === 0 || loading}
          className="inline-flex items-center justify-center rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-40 hover:border-white/20 hover:bg-white/10"
        >
          Previous
        </button>

        <button
          type="button"
          onClick={onNext}
          disabled={!hasMore || loading}
          className="inline-flex items-center justify-center rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-40 hover:border-white/20 hover:bg-white/10"
        >
          Next
        </button>
      </div>
    </aside>
  )
}

function SectionTabs({ activeTab, onTabChange }) {
  return (
    <div className="border-b border-white/10">
      <div role="tablist" aria-label="Dataset sections" className="flex flex-wrap gap-1">
        {TAB_KEYS.map((tab) => {
          let label
          if (tab === 'schema') label = 'Schema'
          else if (tab === 'dimensions') label = 'Dimensions'
          else if (tab === 'measures') label = 'Measures'
          else if (tab === 'preview') label = 'Preview'
          else if (tab === 'query') label = 'Query Builder'
          else label = tab[0].toUpperCase() + tab.slice(1)

          const isSelected = activeTab === tab
          return (
            <button
              type="button"
              key={tab}
              role="tab"
              aria-selected={isSelected}
              onClick={() => onTabChange(tab)}
              className={[
                'rounded-t-2xl px-4 py-3 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--sf-bg)]',
                isSelected
                  ? 'bg-slate-900 text-white shadow-[inset_0_-1px_0_0_rgba(255,255,255,0.08)]'
                  : 'bg-white/5 text-[var(--sf-text-muted)] hover:bg-white/10',
              ].join(' ')}
            >
              {label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function MetricsCard({ label, value, note }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--sf-text-muted)]">
        {label}
      </p>
      <p className="mt-3 text-2xl font-semibold text-white">{value}</p>
      {note && <p className="mt-2 text-sm text-[var(--sf-text-muted)]">{note}</p>}
    </div>
  )
}

function OverviewCard({ summary }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-[0.3em] text-[var(--sf-text-muted)]">Dataset overview</p>
          <h1 className="mt-3 text-2xl font-semibold text-white truncate">{summary.dataset_name}</h1>
          <p className="mt-2 text-sm text-[var(--sf-text-muted)]">{summary.source_name || 'Unknown source'}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-emerald-300">
            Analytics-ready
          </span>
          <span className="rounded-full bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-[var(--sf-text-muted)]">
            {summary.status}
          </span>
        </div>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-[var(--sf-text-muted)]">Rows</p>
          <p className="mt-2 text-xl font-semibold text-white">{formatNumber(summary.row_count)}</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-[var(--sf-text-muted)]">Columns</p>
          <p className="mt-2 text-xl font-semibold text-white">{formatNumber(summary.column_count)}</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-[var(--sf-text-muted)]">Completed</p>
          <p className="mt-2 text-sm text-white">{toLocaleDate(summary.completed_at || summary.created_at)}</p>
        </div>
        {summary.description && (
          <div>
            <p className="text-[11px] uppercase tracking-[0.22em] text-[var(--sf-text-muted)]">Description</p>
            <p className="mt-2 text-sm text-white">{summary.description}</p>
          </div>
        )}
      </div>
    </div>
  )
}

const QUERY_DEFAULT_LIMIT = 100
const QUERY_MAX_LIMIT = 1000
const QUERY_MIN_LIMIT = 1

function QueryBuilder({
  ingestionJobId,
  dimensions,
  measures,
  onClearOnDatasetChange,
}) {
  const [selectedDimensions, setSelectedDimensions] = useState([])
  const [measureRows, setMeasureRows] = useState([
    { id: 1, measure: measures[0]?.identifier || null, aggregation: measures[0]?.supported_aggregations?.[0] || null, alias: '' },
  ])
  const [sortRule, setSortRule] = useState(null)
  const [limit, setLimit] = useState(String(QUERY_DEFAULT_LIMIT))

  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [executedQuery, setExecutedQuery] = useState(null)
  const [resultView, setResultView] = useState('table')
  const [selectedChartType, setSelectedChartType] = useState(null)
  const [dashboardSnapshot, setDashboardSnapshot] = useState(null)

  const controllerRef = useRef(null)
  const requestIdRef = useRef(null)

  const isDirty = useMemo(() => {
    if (!executedQuery) return false
    const currentDimensions = selectedDimensions.map((d) => ({ column_name: d }))
    const currentMeasures = measureRows.map((r) => {
      const m = { aggregation: r.aggregation }
      if (r.measure) m.column_name = r.measure
      if (r.alias) m.alias = r.alias
      return m
    })
    const currentLimit = limit ? Number(limit) : QUERY_DEFAULT_LIMIT

    const dimsChanged = JSON.stringify(currentDimensions) !== JSON.stringify(executedQuery.dimensions)
    const measuresChanged = JSON.stringify(currentMeasures) !== JSON.stringify(executedQuery.measures)
    const sortChanged = JSON.stringify(sortRule ? [sortRule] : []) !== JSON.stringify(executedQuery.sorting || [])
    const limitChanged = currentLimit !== executedQuery.limit

    return dimsChanged || measuresChanged || sortChanged || limitChanged
  }, [selectedDimensions, measureRows, sortRule, limit, executedQuery])

  const compatibility = useMemo(() => {
    if (!result) {
      return {
        supportedChartTypes: [],
        recommendedChart: null,
        recommendation: null,
        defaultCategoryField: null,
        defaultMeasureFields: [],
      }
    }
    return getVisualizationCompatibility(result)
  }, [result])

  const canAddToDashboard = Boolean(result && (selectedChartType || visualizationConfig?.chartType))

  const addVisualizationToDashboard = () => {
    if (!result) return

    setDashboardSnapshot({
      title: `Dashboard snapshot ${new Date().toLocaleTimeString()}`,
      subtitle: `${selectedChartType || visualizationConfig?.chartType || 'visualization'} result`,
      chartType: selectedChartType || visualizationConfig?.chartType || null,
      result,
    })
  }

  const visualizationConfig = useMemo(() => {
    const measureFields = Array.isArray(compatibility.defaultMeasureFields)
      ? compatibility.defaultMeasureFields
      : []
    const safeCategoryField = compatibility.defaultCategoryField || null

    if (!safeCategoryField && measureFields.length === 0) {
      return null
    }

    return {
      chartType: compatibility.recommendedChart || compatibility.supportedChartTypes?.[0] || null,
      categoryField: safeCategoryField,
      measureFields,
    }
  }, [compatibility])

  useEffect(() => {
    setSelectedDimensions([])
    setMeasureRows([ { id: 1, measure: measures[0]?.identifier || null, aggregation: measures[0]?.supported_aggregations?.[0] || null, alias: '' } ])
    setSortRule(null)
    setLimit(String(QUERY_DEFAULT_LIMIT))
    setRunning(false)
    setError(null)
    setResult(null)
    setExecutedQuery(null)
    setResultView('table')
    setSelectedChartType(null)
    if (controllerRef.current) {
      controllerRef.current.abort()
      controllerRef.current = null
    }
    if (typeof onClearOnDatasetChange === 'function') onClearOnDatasetChange()
  }, [ingestionJobId, measures, onClearOnDatasetChange])

  useEffect(() => {
    if (!result) {
      setSelectedChartType(null)
      return
    }

    setSelectedChartType(compatibility.recommendedChart || compatibility.supportedChartTypes?.[0] || null)
  }, [result, compatibility])

  const availableDimensionOptions = useMemo(() => dimensions || [], [dimensions])
  const availableMeasureOptions = useMemo(() => measures || [], [measures])

  const addDimension = (columnName) => {
    if (!columnName) return
    setSelectedDimensions((current) => [...current, columnName])
  }

  const removeDimension = (columnName) => {
    setSelectedDimensions((current) => current.filter((c) => c !== columnName))
  }

  const addMeasureRow = () => {
    setMeasureRows((current) => [...current, { id: Date.now(), measure: null, aggregation: null, alias: '' }])
  }

  const removeMeasureRow = (id) => {
    setMeasureRows((current) => current.filter((r) => r.id !== id))
  }

  const updateMeasureRow = (id, patch) => {
    setMeasureRows((current) => current.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  }

  const _buildRequest = () => {
    const req = {
      dataset_reference: { ingestion_job_id: ingestionJobId },
      dimensions: selectedDimensions.map((d) => ({ column_name: d })),
      measures: measureRows.map((r) => {
        const obj = { aggregation: r.aggregation }
        if (r.measure) obj.column_name = r.measure
        if (r.alias) obj.alias = r.alias
        return obj
      }),
    }
    if (sortRule) req.sorting = [sortRule]
    if (limit) req.limit = Number(limit)
    return req
  }

  const validate = () => {
    const issues = []
    if (!ingestionJobId) issues.push('No dataset selected.')
    if (measureRows.length === 0) issues.push('At least one measure is required.')
    
    const numLimit = limit ? Number(limit) : QUERY_DEFAULT_LIMIT
    if (isNaN(numLimit)) issues.push('Limit must be a number.')
    else if (numLimit < QUERY_MIN_LIMIT) issues.push(`Limit must be at least ${QUERY_MIN_LIMIT}.`)
    else if (numLimit > QUERY_MAX_LIMIT) issues.push(`Limit must not exceed ${QUERY_MAX_LIMIT}.`)

    measureRows.forEach((r, idx) => {
      if (!r.aggregation) issues.push(`Measure row ${idx + 1}: aggregation required.`)
      const measureDef = availableMeasureOptions.find((m) => m.identifier === r.measure)
      if (r.aggregation && measureDef && !measureDef.supported_aggregations.includes(r.aggregation)) {
        issues.push(`Measure row ${idx + 1}: ${AGGREGATION_LABELS[r.aggregation] || r.aggregation} not supported for this measure.`)
      }
      // COUNT and COUNT_DISTINCT handle column_name differently per backend contract
      if (r.aggregation === 'COUNT_DISTINCT' && !r.measure) {
        issues.push(`Measure row ${idx + 1}: COUNT_DISTINCT requires a measure.`)
      }
      if (r.aggregation !== 'COUNT' && r.aggregation !== 'COUNT_DISTINCT' && !r.measure) {
        issues.push(`Measure row ${idx + 1}: ${AGGREGATION_LABELS[r.aggregation] || r.aggregation} requires a measure.`)
      }
    })

    // duplicates
    const dimSet = new Set(selectedDimensions)
    if (dimSet.size !== selectedDimensions.length) issues.push('Duplicate dimensions are not allowed.')

    const pairs = measureRows.map((r) => `${r.measure || ''}::${r.aggregation}`)
    const pairSet = new Set(pairs)
    if (pairSet.size !== pairs.length) issues.push('Duplicate measure + aggregation pairs are not allowed.')

    // Verify sort target is valid
    if (sortRule) {
      const validTargets = new Set([...selectedDimensions])
      measureRows.forEach((r) => {
        if (r.alias) validTargets.add(r.alias)
      })
      if (!validTargets.has(sortRule.target)) {
        issues.push('Sort target is no longer available.')
      }
    }

    return issues
  }

  const runQuery = async () => {
    setError(null)
    const issues = validate()
    if (issues.length > 0) {
      setError(issues.join(' '))
      return
    }

    if (controllerRef.current) {
      controllerRef.current.abort()
    }
    const controller = new AbortController()
    controllerRef.current = controller
    const requestId = Symbol()
    requestIdRef.current = requestId

    setRunning(true)
    try {
      const numLimit = limit ? Number(limit) : QUERY_DEFAULT_LIMIT
      const payload = {
        dataset_reference: { ingestion_job_id: ingestionJobId },
        dimensions: selectedDimensions.map((d) => ({ column_name: d })),
        measures: measureRows.map((r) => {
          const obj = { aggregation: r.aggregation }
          if (r.measure) obj.column_name = r.measure
          if (r.alias) obj.alias = r.alias
          return obj
        }),
        limit: numLimit,
      }
      if (sortRule) payload.sorting = [sortRule]

      const data = await executeAnalyticsQuery(payload, { signal: controller.signal })
      if (requestIdRef.current !== requestId) return
      setResult(data)
      setExecutedQuery(payload)
      setResultView('table')
    } catch (err) {
      if (isRequestCancelled(err)) return
      if (requestIdRef.current !== requestId) return
      setError(err.detail || err.message || 'Query failed')
    } finally {
      if (requestIdRef.current === requestId) requestIdRef.current = null
      setRunning(false)
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--sf-text-muted)]">Build and run an analytics query for the selected dataset. Execution requires an explicit Run action.</p>

      {isDirty && result && (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
          Query changed — run again to see updated results.
        </div>
      )}

      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <h3 className="text-sm font-semibold text-white">Dimensions</h3>
        <p className="mt-1 text-sm text-[var(--sf-text-muted)]">Select zero or more dimensions to group results by.</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {selectedDimensions.length === 0 ? (
            <p className="text-xs text-[var(--sf-text-muted)]">No dimensions selected.</p>
          ) : (
            selectedDimensions.map((d) => (
              <span key={d} className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-3 py-1 text-sm text-[var(--sf-text-muted)]">
                <span>{d}</span>
                <button aria-label={`Remove dimension ${d}`} onClick={() => removeDimension(d)} className="text-xs hover:text-white">×</button>
              </span>
            ))
          )}
        </div>
        <div className="mt-3 flex gap-2">
          <select
            aria-label="Add dimension"
            onChange={(e) => { addDimension(e.target.value); e.target.value = '' }}
            defaultValue=""
            className="rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="" disabled>Choose dimension to add</option>
            {availableDimensionOptions.filter((d) => !selectedDimensions.includes(d.identifier)).map((d) => (
              <option key={d.identifier} value={d.identifier}>{d.display_name || d.identifier} — {d.data_type}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <h3 className="text-sm font-semibold text-white">Measures</h3>
        <p className="mt-1 text-sm text-[var(--sf-text-muted)]">Add one or more measures and choose an aggregation for each.</p>
        <div className="mt-3 space-y-3">
          {measureRows.map((row) => {
            const measureDef = availableMeasureOptions.find((m) => m.identifier === row.measure)
            const aggs = measureDef?.supported_aggregations || []
            return (
              <div key={row.id} className="flex gap-2">
                <select
                  aria-label="Select measure"
                  value={row.measure || ''}
                  onChange={(e) => {
                    const newMeasure = e.target.value || null
                    const newMeasureDef = availableMeasureOptions.find((m) => m.identifier === newMeasure)
                    const validAgg = newMeasureDef?.supported_aggregations?.[0] || null
                    updateMeasureRow(row.id, { measure: newMeasure, aggregation: validAgg })
                  }}
                  className="w-1/3 rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">Choose measure</option>
                  {availableMeasureOptions.map((m) => (
                    <option key={m.identifier} value={m.identifier}>{m.display_name || m.identifier}</option>
                  ))}
                </select>

                <select
                  aria-label="Select aggregation"
                  value={row.aggregation || ''}
                  onChange={(e) => updateMeasureRow(row.id, { aggregation: e.target.value || null })}
                  className="w-1/3 rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">Choose aggregation</option>
                  {aggs.map((a) => (
                    <option key={a} value={a}>{AGGREGATION_LABELS[a] || a}</option>
                  ))}
                  {row.measure ? null : <option value="COUNT">Count (rows)</option>}
                </select>

                <input
                  aria-label="Alias"
                  placeholder="alias (optional)"
                  value={row.alias}
                  onChange={(e) => updateMeasureRow(row.id, { alias: e.target.value })}
                  className="w-1/3 rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-[var(--sf-text-muted)] focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />

                {measureRows.length > 1 && (
                  <button type="button" aria-label="Remove measure" onClick={() => removeMeasureRow(row.id)} className="ml-2 rounded-lg bg-red-600/20 px-3 py-2 text-sm text-red-300 hover:bg-red-600/30">Remove</button>
                )}
              </div>
            )
          })}
        </div>
        <div className="mt-3">
          <button type="button" onClick={addMeasureRow} className="rounded-lg bg-indigo-500/20 px-4 py-2 text-sm font-semibold text-indigo-300 hover:bg-indigo-500/30">Add measure</button>
        </div>
      </div>

      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <h3 className="text-sm font-semibold text-white">Sorting & limit</h3>
        <p className="mt-1 text-sm text-[var(--sf-text-muted)]">Optional: Sort results and set row limit.</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <div>
            <label htmlFor="sort-target" className="text-xs font-semibold text-[var(--sf-text-muted)]">Sort by</label>
            <select
              id="sort-target"
              aria-label="Sort target"
              value={sortRule?.target || ''}
              onChange={(e) => setSortRule(e.target.value ? { target: e.target.value, direction: sortRule?.direction || 'DESCENDING' } : null)}
              className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">No sorting</option>
              {selectedDimensions.map((d) => <option key={`d-${d}`} value={d}>Dimension: {d}</option>)}
              {measureRows.map((r) => (r.alias ? <option key={`m-${r.id}`} value={r.alias}>Measure: {r.alias}</option> : null))}
            </select>
          </div>

          <div>
            <label htmlFor="sort-direction" className="text-xs font-semibold text-[var(--sf-text-muted)]">Direction</label>
            <select
              id="sort-direction"
              aria-label="Sort direction"
              value={sortRule?.direction || 'DESCENDING'}
              onChange={(e) => setSortRule((s) => s ? { ...s, direction: e.target.value } : null)}
              disabled={!sortRule}
              className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="DESCENDING">Descending</option>
              <option value="ASCENDING">Ascending</option>
            </select>
          </div>
        </div>

        <div className="mt-3">
          <label htmlFor="query-limit" className="text-xs font-semibold text-[var(--sf-text-muted)]">Row limit (1–{QUERY_MAX_LIMIT})</label>
          <input
            id="query-limit"
            type="number"
            min={QUERY_MIN_LIMIT}
            max={QUERY_MAX_LIMIT}
            placeholder={String(QUERY_DEFAULT_LIMIT)}
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-[var(--sf-text-muted)] focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button onClick={runQuery} disabled={running} className={['rounded-2xl px-4 py-2 font-semibold', running ? 'bg-indigo-500/30 text-indigo-200 opacity-70 cursor-not-allowed' : 'bg-indigo-500 text-white hover:bg-indigo-600'].join(' ')}>
          {running ? 'Running…' : 'Run query'}
        </button>
        <button onClick={() => { setSelectedDimensions([]); setMeasureRows([{ id: 1, measure: measures[0]?.identifier || null, aggregation: measures[0]?.supported_aggregations?.[0] || null, alias: '' }]); setSortRule(null); setLimit(String(QUERY_DEFAULT_LIMIT)); setResult(null); setError(null); setDashboardSnapshot(null) }} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm hover:bg-white/10">Reset</button>
        {error && <div className="ml-4 flex-1 text-sm text-rose-400">{error}</div>}
      </div>

      {!running && result && (
        <div className="mt-6 space-y-4">
          <div className="flex items-center gap-4 rounded-2xl border border-white/10 bg-white/5 p-4">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-[var(--sf-text-muted)]">Rows returned</p>
              <p className="mt-2 text-xl font-semibold text-white">{result.row_count ?? result.returned_count ?? 0}</p>
            </div>
            {result.limit && (
              <div>
                <p className="text-xs uppercase tracking-[0.22em] text-[var(--sf-text-muted)]">Limit</p>
                <p className="mt-2 text-sm text-white">{result.limit}</p>
              </div>
            )}
            {result.has_more && (
              <div className="text-xs text-amber-300">
                (More results available; query limit reached)
              </div>
            )}
          </div>

          <VisualizationToolbar
            currentView={resultView}
            onViewChange={setResultView}
            chartType={selectedChartType || visualizationConfig?.chartType || null}
            onChartTypeChange={setSelectedChartType}
            supportedChartTypes={compatibility.supportedChartTypes || []}
            recommendation={compatibility.recommendation}
            disabled={!result}
          />

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={addVisualizationToDashboard}
              disabled={!canAddToDashboard}
              className="rounded-2xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Add to dashboard
            </button>
            <span className="text-sm text-[var(--sf-text-muted)]">
              Reuse the current visualization state without rerunning the query.
            </span>
          </div>

          {resultView === 'visualization' ? (
            <AnalyticsVisualization result={result} chartType={selectedChartType || visualizationConfig?.chartType || null} />
          ) : (
            <div className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/40">
              <table className="min-w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="bg-white/5 text-[var(--sf-text-muted)]">
                    {result.columns.map((c) => (
                      <th key={c.identifier || c} className="px-4 py-3 font-semibold">{c.label || c.display_name || c.identifier || c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.length === 0 ? (
                    <tr><td className="px-4 py-6 text-sm text-[var(--sf-text-muted)]" colSpan={result.columns.length}>Query returned no rows.</td></tr>
                  ) : (
                    result.rows.map((row, idx) => (
                      <tr key={idx} className="border-t border-white/5">
                        {result.columns.map((c) => (
                          <td key={c.identifier || c} className="px-4 py-3 text-[var(--sf-text-muted)]">{safeCellValue(row[c.identifier || c])}</td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          <DashboardWorkspace snapshot={dashboardSnapshot} />
        </div>
      )}
    </div>
  )
}

export default function AnalyticsPage() {
  const [datasets, setDatasets] = useState([])
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedDatasetId, setSelectedDatasetId] = useState(null)
  const [activeTab, setActiveTab] = useState('schema')

  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState(null)
  const [listReloadKey, setListReloadKey] = useState(0)

  const [detailsState, setDetailsState] = useState({ loading: false, error: null, data: null })
  const [statisticsState, setStatisticsState] = useState({ loading: false, error: null, data: null })
  const [schemaState, setSchemaState] = useState({ loading: false, error: null, data: [] })
  const [dimensionsState, setDimensionsState] = useState({ loading: false, error: null, data: [] })
  const [measuresState, setMeasuresState] = useState({ loading: false, error: null, data: [] })
  const [previewState, setPreviewState] = useState({ loading: false, error: null, data: null })
  const [selectedReloadKey, setSelectedReloadKey] = useState(0)

  const selectedRequestRef = useRef(null)

  const retryDatasetList = useCallback(() => setListReloadKey((current) => current + 1), [])
  const retrySelectedDataset = useCallback(() => setSelectedReloadKey((current) => current + 1), [])

  const loadDatasets = useCallback(async (signal) => {
    setListLoading(true)
    setListError(null)

    try {
      const result = await listAnalyticsDatasets({ limit: PAGE_SIZE, offset, signal })
      setDatasets(result.items)
      setTotal(result.total)
      setHasMore(result.has_more)
      setSelectedDatasetId((currentSelected) => currentSelected ?? (result.items[0]?.ingestion_job_id ?? null))
    } catch (error) {
      if (!isRequestCancelled(error)) {
        setListError(error.detail || error.message || 'Unable to load datasets.')
      }
    } finally {
      setListLoading(false)
    }
  }, [offset])

  useEffect(() => {
    const controller = new AbortController()
    loadDatasets(controller.signal)
    return () => controller.abort()
  }, [loadDatasets, listReloadKey])

  useEffect(() => {
    if (!selectedDatasetId) return
    setActiveTab('schema')
    const controller = new AbortController()
    const requestId = Symbol()
    selectedRequestRef.current = requestId

    const loadSection = async (loader, setter) => {
      setter({ loading: true, error: null, data: null })
      try {
        const result = await loader()
        if (selectedRequestRef.current !== requestId) return
        setter({ loading: false, error: null, data: result })
      } catch (error) {
        if (isRequestCancelled(error)) return
        if (selectedRequestRef.current !== requestId) return
        setter({ loading: false, error: error.detail || error.message || 'Unable to load data.', data: null })
      }
    }

    loadSection(() => getDatasetDetails(selectedDatasetId, { signal: controller.signal }), setDetailsState)
    loadSection(() => getDatasetStatistics(selectedDatasetId, { signal: controller.signal }), setStatisticsState)
    loadSection(() => getDatasetSchema(selectedDatasetId, { signal: controller.signal }), setSchemaState)
    loadSection(() => getDatasetDimensions(selectedDatasetId, { signal: controller.signal }), setDimensionsState)
    loadSection(() => getDatasetMeasures(selectedDatasetId, { signal: controller.signal }), setMeasuresState)
    loadSection(() => getDatasetPreview(selectedDatasetId, PREVIEW_LIMIT, { signal: controller.signal }), setPreviewState)

    return () => {
      selectedRequestRef.current = null
      controller.abort()
    }
  }, [selectedDatasetId, selectedReloadKey])

  const selectedTabError = {
    schema: schemaState.error,
    dimensions: dimensionsState.error,
    measures: measuresState.error,
    preview: previewState.error,
  }[activeTab]

  const selectedTabLoading = {
    schema: schemaState.loading,
    dimensions: dimensionsState.loading,
    measures: measuresState.loading,
    preview: previewState.loading,
  }[activeTab]

  const showWorkspacePlaceholder = !selectedDatasetId && !listLoading && !listError

  return (
    <AppShell>
      <div className="grid gap-6 lg:grid-cols-[360px_1fr] xl:grid-cols-[380px_1fr]">
        <DatasetBrowser
          datasets={datasets}
          total={total}
          limit={PAGE_SIZE}
          offset={offset}
          hasMore={hasMore}
          loading={listLoading}
          error={listError}
          selectedDatasetId={selectedDatasetId}
          searchTerm={searchTerm}
          onSearch={(value) => {
            setSearchTerm(value)
            if (offset !== 0) setOffset(0)
          }}
          onPrevious={() => setOffset((current) => Math.max(current - PAGE_SIZE, 0))}
          onNext={() => setOffset((current) => current + PAGE_SIZE)}
          onRetry={retryDatasetList}
          onSelect={setSelectedDatasetId}
        />

        <div className="flex flex-col gap-6">
          <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-semibold text-white">Analytics Workspace</p>
                <p className="text-sm text-[var(--sf-text-muted)]">
                  Inspect the selected dataset, review its schema, dimensions, measures, and preview.
                </p>
              </div>
              <div className="rounded-full bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-[var(--sf-text-muted)]">
                Next step: Build analytics query
              </div>
            </div>
          </div>

          {showWorkspacePlaceholder && (
            <div className="rounded-3xl border border-white/10 bg-white/5 p-8 text-center text-sm text-[var(--sf-text-muted)]">
              <p className="text-white">Select a dataset from the browser to see its analytics metadata.</p>
            </div>
          )}

          {selectedDatasetId && (
            <>
              {detailsState.loading && !detailsState.data ? (
                <LoadingState message="Loading dataset details…" />
              ) : detailsState.error && !detailsState.data ? (
                <ErrorState
                  message={detailsState.error}
                  onRetry={retrySelectedDataset}
                />
              ) : detailsState.data ? (
                <>
                  <OverviewCard summary={detailsState.data.summary} />

                  <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <MetricsCard label="Total rows" value={formatNumber(statisticsState.data?.row_count ?? detailsState.data.summary.row_count)} />
                        <MetricsCard label="Total columns" value={formatNumber(statisticsState.data?.column_count ?? detailsState.data.summary.column_count)} />
                        <MetricsCard label="Numeric columns" value={formatNumber(statisticsState.data?.numeric_column_count ?? 0)} />
                        <MetricsCard label="Text columns" value={formatNumber(statisticsState.data?.text_column_count ?? 0)} />
                        <MetricsCard label="Date / datetime" value={`${formatNumber((statisticsState.data?.date_column_count ?? 0) + (statisticsState.data?.datetime_column_count ?? 0))}`} />
                        <MetricsCard label="Boolean columns" value={formatNumber(statisticsState.data?.boolean_column_count ?? 0)} />
                        <MetricsCard label="Nullable columns" value={formatNumber(statisticsState.data?.nullable_column_count ?? 0)} />
                      </div>

                      <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
                        <SectionTabs activeTab={activeTab} onTabChange={setActiveTab} />

                        <div className="mt-6">
                          {selectedTabLoading && <LoadingState message="Loading section…" />}
                          {selectedTabError && !selectedTabLoading && (
                            <ErrorState
                              message={selectedTabError}
                              onRetry={retrySelectedDataset}
                            />
                          )}

                          {!selectedTabLoading && !selectedTabError && activeTab === 'schema' && (
                            <div className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/40">
                              <table className="min-w-full border-collapse text-left text-sm">
                                <thead>
                                  <tr className="bg-white/5 text-[var(--sf-text-muted)]">
                                    <th className="px-4 py-3 font-semibold">Identifier</th>
                                    <th className="px-4 py-3 font-semibold">Display name</th>
                                    <th className="px-4 py-3 font-semibold">Type</th>
                                    <th className="px-4 py-3 font-semibold">Nullable</th>
                                    <th className="px-4 py-3 font-semibold">Dimension</th>
                                    <th className="px-4 py-3 font-semibold">Measure</th>
                                    <th className="px-4 py-3 font-semibold">Aggregations</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {schemaState.data.length === 0 ? (
                                    <tr>
                                      <td colSpan="7" className="px-4 py-6 text-sm text-[var(--sf-text-muted)]">
                                        No persisted column metadata found.
                                      </td>
                                    </tr>
                                  ) : (
                                    schemaState.data.map((column) => (
                                      <tr key={column.identifier} className="border-t border-white/5">
                                        <td className="px-4 py-3 text-white">{column.identifier}</td>
                                        <td className="px-4 py-3 text-[var(--sf-text-muted)]">{column.display_name}</td>
                                        <td className="px-4 py-3 text-[var(--sf-text-muted)]">{column.inferred_type}</td>
                                        <td className="px-4 py-3 text-[var(--sf-text-muted)]">{column.nullable ? 'Yes' : 'No'}</td>
                                        <td className="px-4 py-3 text-[var(--sf-text-muted)]">{column.dimension_eligible ? 'Yes' : 'No'}</td>
                                        <td className="px-4 py-3 text-[var(--sf-text-muted)]">{column.measure_eligible ? 'Yes' : 'No'}</td>
                                        <td className="px-4 py-3 text-[var(--sf-text-muted)]">
                                          {column.supported_aggregations.length > 0
                                            ? column.supported_aggregations.map((agg) => (
                                              <span
                                                key={agg}
                                                className="mr-2 inline-flex rounded-full bg-slate-900 px-2 py-1 text-[11px] uppercase tracking-[0.22em] text-[var(--sf-text-muted)]"
                                              >
                                                {AGGREGATION_LABELS[agg] || agg}
                                              </span>
                                            ))
                                            : 'None'}
                                        </td>
                                      </tr>
                                    ))
                                  )}
                                </tbody>
                              </table>
                            </div>
                          )}

                          {!selectedTabLoading && !selectedTabError && activeTab === 'dimensions' && (
                            <div className="space-y-4">
                              <p className="text-sm text-[var(--sf-text-muted)]">
                                Dimensions group or segment analytics results. Only columns that are eligible for grouping are shown.
                              </p>
                              {dimensionsState.data.length === 0 ? (
                                <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-sm text-[var(--sf-text-muted)]">
                                  No eligible dimensions available for this dataset.
                                </div>
                              ) : (
                                <div className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/40">
                                  <table className="min-w-full border-collapse text-left text-sm">
                                    <thead>
                                      <tr className="bg-white/5 text-[var(--sf-text-muted)]">
                                        <th className="px-4 py-3 font-semibold">Identifier</th>
                                        <th className="px-4 py-3 font-semibold">Display name</th>
                                        <th className="px-4 py-3 font-semibold">Type</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {dimensionsState.data.map((item) => (
                                        <tr key={item.identifier} className="border-t border-white/5">
                                          <td className="px-4 py-3 text-white">{item.identifier}</td>
                                          <td className="px-4 py-3 text-[var(--sf-text-muted)]">{item.display_name}</td>
                                          <td className="px-4 py-3 text-[var(--sf-text-muted)]">{item.data_type}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </div>
                          )}

                          {!selectedTabLoading && !selectedTabError && activeTab === 'measures' && (
                            <div className="space-y-4">
                              <p className="text-sm text-[var(--sf-text-muted)]">
                                Measures show columns that support aggregations. Use these metrics in future analytics queries.
                              </p>
                              {measuresState.data.length === 0 ? (
                                <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-sm text-[var(--sf-text-muted)]">
                                  No supported measures available for this dataset.
                                </div>
                              ) : (
                                <div className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/40">
                                  <table className="min-w-full border-collapse text-left text-sm">
                                    <thead>
                                      <tr className="bg-white/5 text-[var(--sf-text-muted)]">
                                        <th className="px-4 py-3 font-semibold">Identifier</th>
                                        <th className="px-4 py-3 font-semibold">Display name</th>
                                        <th className="px-4 py-3 font-semibold">Type</th>
                                        <th className="px-4 py-3 font-semibold">Aggregations</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {measuresState.data.map((item) => (
                                        <tr key={item.identifier} className="border-t border-white/5">
                                          <td className="px-4 py-3 text-white">{item.identifier}</td>
                                          <td className="px-4 py-3 text-[var(--sf-text-muted)]">{item.display_name}</td>
                                          <td className="px-4 py-3 text-[var(--sf-text-muted)]">{item.data_type}</td>
                                          <td className="px-4 py-3 text-[var(--sf-text-muted)]">
                                            {item.supported_aggregations.map((agg) => (
                                              <span
                                                key={agg}
                                                className="mr-2 inline-flex rounded-full bg-slate-900 px-2 py-1 text-[11px] uppercase tracking-[0.22em] text-[var(--sf-text-muted)]"
                                              >
                                                {AGGREGATION_LABELS[agg] || agg}
                                              </span>
                                            ))}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </div>
                          )}

                          {!selectedTabLoading && !selectedTabError && activeTab === 'preview' && (
                            <div className="space-y-4">
                              <p className="text-sm text-[var(--sf-text-muted)]">
                                Preview shows a safe sample of persisted rows. The backend limits previews to 50 rows.
                              </p>
                              {previewState.data && previewState.data.rows.length === 0 ? (
                                <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-sm text-[var(--sf-text-muted)]">
                                  This dataset has no persisted rows to preview.
                                </div>
                              ) : (
                                <div className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/40">
                                  <table className="min-w-full border-collapse text-left text-sm">
                                    <thead>
                                      <tr className="bg-white/5 text-[var(--sf-text-muted)]">
                                        {previewState.data?.columns.map((column) => (
                                          <th key={column} className="px-4 py-3 font-semibold">{column}</th>
                                        ))}
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {previewState.data?.rows.map((row, index) => (
                                        <tr key={index} className="border-t border-white/5">
                                          {previewState.data.columns.map((column) => (
                                            <td key={column} className="px-4 py-3 text-[var(--sf-text-muted)]">
                                              {safeCellValue(row[column])}
                                            </td>
                                          ))}
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </div>
                          )}

                          {!selectedTabLoading && !selectedTabError && activeTab === 'query' && (
                            <div className="space-y-4">
                              <QueryBuilder
                                ingestionJobId={selectedDatasetId}
                                dimensions={dimensionsState.data}
                                measures={measuresState.data}
                                onClearOnDatasetChange={() => {}}
                              />
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
                        <p className="text-sm text-[var(--sf-text-muted)] uppercase tracking-[0.3em]">Next workflow</p>
                        <p className="mt-4 text-sm text-white">
                          The analytics query builder will be added in a future release. For now, this workspace helps you discover dataset metadata and preview rows.
                        </p>
                        <button
                          type="button"
                          disabled
                          className="mt-6 inline-flex w-full items-center justify-center rounded-2xl bg-indigo-500/20 px-4 py-2 text-sm font-semibold text-indigo-200 opacity-70"
                        >
                          Build analytics query (coming soon)
                        </button>
                      </div>
                    </div>
                  </div>
                </>
              ) : null}
            </>
          )}
        </div>
      </div>
    </AppShell>
  )
}
