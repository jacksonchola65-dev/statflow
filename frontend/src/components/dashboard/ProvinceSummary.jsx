import EmptyState from '../common/EmptyState'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import ProvinceComparisonChart from './ProvinceComparisonChart'

/**
 * ProvinceSummary — card wrapper around ProvinceComparisonChart.
 *
 * Visual changes from previous version:
 *  - Card surface: bg-slate-800/60 (was bg-gray-900)
 *  - Card border: border-[var(--sf-border)] (was border-white/10)
 *  - Hover shadow transition added
 *  - Eyebrow label: token typography (text-[11px] tracking-[--sf-tracking-widest])
 *  - Section title: text-xl font-semibold (was text-lg)
 *  - Unit badge: text-[var(--sf-text-muted)] (was text-gray-400)
 *
 * All prop names and rendering logic are unchanged.
 *
 * @param {{
 *   loading:               boolean,
 *   error:                 string | null,
 *   chartData:             Array,
 *   unit:                  string,
 *   selectedProvince:      string,
 *   selectedIndicatorName: string,
 *   selectedYear:          number,
 * }} props
 */
export default function ProvinceSummary({
  loading,
  error,
  chartData,
  unit,
  selectedProvince,
  selectedIndicatorName,
  selectedYear,
}) {
  return (
    <section
      className="
        rounded-xl
        border border-[var(--sf-border)]
        bg-slate-800/60
        p-4 sm:p-6
        shadow-[var(--sf-shadow-card)]
        hover:shadow-[var(--sf-shadow-card-hover)]
        transition-shadow duration-200
      "
    >
      {/* Header */}
      <div className="mb-6">
        <p
          className="
            text-[11px] font-medium uppercase
            tracking-[var(--sf-tracking-widest)]
            text-[var(--sf-text-subtle)]
            mb-1
          "
        >
          Province-level comparison · {selectedYear}
        </p>
        <h2 className="text-xl font-semibold text-white leading-tight">
          {selectedIndicatorName || 'Select an indicator'}
          {unit && (
            <span className="ml-2 text-sm font-normal text-[var(--sf-text-muted)]">
              ({unit})
            </span>
          )}
        </h2>
      </div>

      {/* States */}
      {loading && <LoadingState />}

      {!loading && error && (
        <div className="flex items-center justify-center h-64">
          <ErrorState message={error} />
        </div>
      )}

      {!loading && !error && chartData.length === 0 && <EmptyState />}

      {!loading && !error && chartData.length > 0 && (
        <ProvinceComparisonChart
          data={chartData}
          unit={unit}
          selectedProvince={selectedProvince}
        />
      )}
    </section>
  )
}
