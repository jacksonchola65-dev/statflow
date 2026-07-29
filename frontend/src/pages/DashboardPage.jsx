import { useMemo } from 'react'
import AppShell from '../components/layout/AppShell'
import ErrorState from '../components/common/ErrorState'
import DashboardFilters from '../components/dashboard/DashboardFilters'
import DashboardFooter from '../components/common/DashboardFooter'
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

  return (
    <AppShell>
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
