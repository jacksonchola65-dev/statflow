import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/layout/AppShell'
import ErrorState from '../components/common/ErrorState'
import DashboardFilters from '../components/dashboard/DashboardFilters'
import DashboardFooter from '../components/common/DashboardFooter'
import { useAuth } from '../contexts/AuthContext'
import KpiGrid from '../components/dashboard/KpiGrid'
import ProvinceSummary from '../components/dashboard/ProvinceSummary'
import DataTable from '../components/dashboard/DataTable'
import ZambiaProvinceMap from '../components/dashboard/ZambiaProvinceMap'
import { useDashboardFilters } from '../hooks/useDashboardFilters'
import { useIndicatorSummary } from '../hooks/useIndicatorSummary'

// ---------------------------------------------------------------------------
// Inline SVG icons (aria-hidden — decorative only)
// ---------------------------------------------------------------------------

function IconChartBar() {
  return (
    <svg
      aria-hidden="true"
      width="20" height="20"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path d="M2 11a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-5zm6-4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V7zm6-3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1V4z" />
    </svg>
  )
}

function IconArrowUp() {
  return (
    <svg
      aria-hidden="true"
      width="20" height="20"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M10 17a.75.75 0 0 1-.75-.75V5.612L5.29 9.77a.75.75 0 0 1-1.08-1.04l5.25-5.5a.75.75 0 0 1 1.08 0l5.25 5.5a.75.75 0 1 1-1.08 1.04L10.75 5.612V16.25A.75.75 0 0 1 10 17z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function IconArrowDown() {
  return (
    <svg
      aria-hidden="true"
      width="20" height="20"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M10 3a.75.75 0 0 1 .75.75v10.638l3.96-4.158a.75.75 0 1 1 1.08 1.04l-5.25 5.5a.75.75 0 0 1-1.08 0l-5.25-5.5a.75.75 0 1 1 1.08-1.04l3.96 4.158V3.75A.75.75 0 0 1 10 3z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function IconMapPin() {
  return (
    <svg
      aria-hidden="true"
      width="20" height="20"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M9.69 18.933l.003.001C9.89 19.02 10 19 10 19s.11.02.308-.066l.002-.001.006-.003.018-.008a5.741 5.741 0 0 0 .281-.14c.186-.096.446-.24.757-.433.62-.384 1.445-.966 2.274-1.765C15.302 14.988 17 12.493 17 9A7 7 0 1 0 3 9c0 3.492 1.698 5.988 3.355 7.584a13.731 13.731 0 0 0 2.273 1.765 11.842 11.842 0 0 0 .976.544l.062.029.018.008.006.003zM10 11.25a2.25 2.25 0 1 0 0-4.5 2.25 2.25 0 0 0 0 4.5z"
        clipRule="evenodd"
      />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// KPI computation helper
// ---------------------------------------------------------------------------

/**
 * Derives four KPI items from the unfiltered summary results.
 * Returns null when results is empty so KpiGrid renders nothing.
 *
 * @param {Array}  results  summary.results array
 * @param {string} unit     unit string (e.g. "%", "Percent")
 * @returns {Array|null}
 */
function computeKpiItems(results, unit) {
  if (!results || results.length === 0) return null

  const values = results.map((r) => parseFloat(r.value))
  const total  = values.length

  // National Average — arithmetic mean
  const avg    = values.reduce((sum, v) => sum + v, 0) / total

  // Highest Province
  const maxVal = Math.max(...values)
  const maxIdx = values.indexOf(maxVal)

  // Lowest Province
  const minVal = Math.min(...values)
  const minIdx = values.indexOf(minVal)

  // Coverage — provinces with valid numeric data out of 10
  const TOTAL_PROVINCES = 10

  return [
    {
      label:   'National Average',
      value:   avg.toFixed(1),
      unit,
      icon:    <IconChartBar />,
      variant: 'primary',
    },
    {
      label:    'Highest Province',
      value:    maxVal.toLocaleString(undefined, { maximumFractionDigits: 1 }),
      unit,
      subtitle: results[maxIdx]?.province_name ?? '',
      icon:     <IconArrowUp />,
      variant:  'success',
    },
    {
      label:    'Lowest Province',
      value:    minVal.toLocaleString(undefined, { maximumFractionDigits: 1 }),
      unit,
      subtitle: results[minIdx]?.province_name ?? '',
      icon:     <IconArrowDown />,
      variant:  'danger',
    },
    {
      label:   'Coverage',
      value:   `${total} / ${TOTAL_PROVINCES}`,
      icon:    <IconMapPin />,
      variant: 'info',
    },
  ]
}

// ---------------------------------------------------------------------------
// DashboardPage
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [question, setQuestion] = useState('')
  const {
    provinces,
    indicators,
    refLoading,
    refError,
    selectedProvince,
    setSelectedProvince,
    selectedIndicatorId,
    setSelectedIndicatorId,
    selectedYear,
    setSelectedYear,
    loadRefData,
  } = useDashboardFilters()

  const { loading: chartLoading, error: chartError, chartData, summary } =
    useIndicatorSummary({
      indicatorId:   selectedIndicatorId,
      year:          selectedYear,
      provinceFilter: selectedProvince,
    })

  const selectedIndicator = indicators.find((i) => i.id === selectedIndicatorId)
  const unit = summary?.unit ?? selectedIndicator?.unit ?? ''

  // KPI items computed from the UNFILTERED results (summary.results, not chartData)
  // so the stats always reflect all provinces regardless of the province filter.
  const kpiItems = useMemo(
    () => computeKpiItems(summary?.results ?? [], unit),
    [summary?.results, unit],
  )

  const firstName = user?.full_name?.trim().split(/\s+/)[0]
  const greeting = firstName || 'there'
  const userCanImport = ['ADMIN', 'DATA_MANAGER'].includes(user?.role)

  const askStatFlow = (event) => {
    event.preventDefault()
    navigate('/decisions', { state: { query: question.trim() } })
  }

  return (
    <AppShell>
      <section className="mb-8 border border-cyan-300/20 bg-slate-900 px-5 py-7 shadow-[var(--sf-shadow-card)] sm:px-8 sm:py-9" aria-labelledby="dashboard-welcome-heading">
        <div className="max-w-4xl">
          <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-cyan-300">Evidence and decision intelligence</p>
          <h1 id="dashboard-welcome-heading" className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">Good morning, {greeting}</h1>
          <p className="mt-3 max-w-2xl text-base leading-7 text-slate-300">Turn trusted public evidence and your organization&apos;s permitted data into insights that help you decide what to do next.</p>

          <form className="mt-6 flex flex-col gap-3 sm:flex-row" onSubmit={askStatFlow}>
            <label htmlFor="dashboard-question" className="sr-only">Ask StatFlow about data, places or decisions</label>
            <input
              id="dashboard-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask StatFlow about data, places or decisions..."
              className="min-h-12 min-w-0 flex-1 border border-white/15 bg-slate-950 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-cyan-300 focus:outline-none focus:ring-2 focus:ring-cyan-300/40"
            />
            <button type="submit" className="min-h-12 rounded-lg bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition-colors hover:bg-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900">
              Ask StatFlow
            </button>
          </form>

          <div className="mt-5 border-l-2 border-emerald-400/60 bg-emerald-400/[0.06] px-4 py-3 text-sm text-slate-300">
            <p className="font-semibold text-emerald-200">Available now</p>
            <button type="button" onClick={() => navigate('/decisions')} className="mt-1 text-left text-white underline decoration-white/20 underline-offset-4 hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300">
              Which district in Luapula is best for opening a supermarket?
            </button>
          </div>
        </div>
      </section>

      <section className="mb-8 grid gap-4 md:grid-cols-3" aria-label="StatFlow primary paths">
        <button type="button" onClick={() => navigate('/decisions')} className="group rounded-xl border border-white/10 bg-slate-900 p-5 text-left transition-colors hover:border-cyan-300/50 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-300">01 / Decide</p>
          <h2 className="mt-2 text-lg font-semibold text-white">Make a decision</h2>
          <p className="mt-2 text-sm leading-6 text-slate-400">Use available evidence to evaluate alternatives and support a decision.</p>
          <span className="mt-4 inline-block text-sm font-semibold text-cyan-200">Open Decision Workspace</span>
        </button>
        <button type="button" onClick={() => navigate('/analytics')} className="group rounded-xl border border-white/10 bg-slate-900 p-5 text-left transition-colors hover:border-cyan-300/50 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-300">02 / Understand</p>
          <h2 className="mt-2 text-lg font-semibold text-white">Explore evidence</h2>
          <p className="mt-2 text-sm leading-6 text-slate-400">Explore available public, official, and permitted organizational data.</p>
          <span className="mt-4 inline-block text-sm font-semibold text-cyan-200">Open Analytics</span>
        </button>
        {userCanImport ? (
          <button type="button" onClick={() => navigate('/import')} className="group rounded-xl border border-white/10 bg-slate-900 p-5 text-left transition-colors hover:border-cyan-300/50 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-300">03 / Contribute</p>
            <h2 className="mt-2 text-lg font-semibold text-white">Bring your data</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">Upload organizational data and prepare it for analysis and decision support.</p>
            <span className="mt-4 inline-block text-sm font-semibold text-cyan-200">Open Data Import</span>
          </button>
        ) : (
          <div className="rounded-xl border border-white/10 bg-slate-900 p-5" aria-label="Bring your data unavailable">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">03 / Contribute</p>
            <h2 className="mt-2 text-lg font-semibold text-white">Bring your data</h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">Organizational data import is available to permitted data teams.</p>
            <span className="mt-4 inline-block text-sm text-slate-500">Permission required</span>
          </div>
        )}
      </section>

      <section className="mb-8 border border-white/10 bg-slate-950/60 px-5 py-4 sm:px-6" aria-labelledby="future-direction-heading">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-300">Product direction</p>
            <h2 id="future-direction-heading" className="mt-1 text-base font-semibold text-white">More decision families are ahead</h2>
          </div>
          <p className="max-w-2xl text-sm leading-6 text-slate-400">Examples such as hospital planning, school placement, infrastructure prioritization, and bank expansion are upcoming capabilities, not active production analyses.</p>
        </div>
      </section>

      {/* Reference data error with Retry */}
      {refError && (
        <ErrorState
          message={refError}
          onRetry={loadRefData}
          retrying={refLoading}
        />
      )}

      {/* KPI grid — renders only when data is available */}
      <KpiGrid items={kpiItems} />

      {/* Filters */}
      <DashboardFilters
        provinces={provinces}
        indicators={indicators}
        selectedProvince={selectedProvince}
        selectedIndicatorId={selectedIndicatorId}
        selectedYear={selectedYear}
        disabled={refLoading}
        onProvinceChange={setSelectedProvince}
        onIndicatorChange={setSelectedIndicatorId}
        onYearChange={setSelectedYear}
      />

      {/* Choropleth map — receives unfiltered results so all provinces are coloured */}
      <ZambiaProvinceMap
        chartData={summary?.results ?? []}
        provinces={provinces}
        selectedProvince={selectedProvince}
        onProvinceSelect={setSelectedProvince}
        unit={unit}
        loading={refLoading || chartLoading}
        error={chartError}
      />

      {/* Chart */}
      <ProvinceSummary
        loading={refLoading || chartLoading}
        error={chartError}
        chartData={chartData}
        unit={unit}
        selectedProvince={selectedProvince}
        selectedIndicatorName={selectedIndicator?.name ?? ''}
        selectedYear={selectedYear}
      />

      {/* Data table */}
      <DataTable rows={chartData} unit={unit} />

      {/* Footer — replaces the standalone disclaimer paragraph */}
      <DashboardFooter
        year={selectedYear}
        indicatorName={selectedIndicator?.name}
      />
    </AppShell>
  )
}
