import SelectField from '../common/SelectField'

const AVAILABLE_YEARS = [2023, 2022, 2021, 2020]

/**
 * DashboardFilters — Province / Indicator / Year selects wrapped in a
 * professional card panel.
 *
 * Visual changes from previous version:
 *  - Outer container is now a card: rounded-xl, token border, token surface,
 *    consistent padding, and bottom margin using the 8 px spacing scale
 *  - "Filters" eyebrow label added above the grid for context
 *  - Responsive grid: 1 column on xs, 3 columns on sm+
 *
 * All prop names, callback signatures, and filter logic are unchanged.
 *
 * @param {{
 *   provinces:           Array<{id: string, name: string}>,
 *   indicators:          Array<{id: string, name: string}>,
 *   selectedProvince:    string,
 *   selectedIndicatorId: string,
 *   selectedYear:        number,
 *   disabled:            boolean,
 *   onProvinceChange:    (v: string) => void,
 *   onIndicatorChange:   (v: string) => void,
 *   onYearChange:        (v: number) => void,
 * }} props
 */
export default function DashboardFilters({
  provinces,
  indicators,
  selectedProvince,
  selectedIndicatorId,
  selectedYear,
  disabled,
  onProvinceChange,
  onIndicatorChange,
  onYearChange,
}) {
  return (
    <section
      className="
        rounded-xl
        border border-[var(--sf-border)]
        bg-slate-800/60
        p-4 sm:p-5
        mb-6
      "
      aria-label="Dashboard filters"
    >
      {/* Eyebrow label */}
      <p
        className="
          text-[10px] font-semibold uppercase
          tracking-[var(--sf-tracking-widest)]
          text-[var(--sf-text-subtle)]
          mb-4
        "
      >
        Filters
      </p>

      {/* Select grid — 1 col on xs, 3 cols on sm+ */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <SelectField
          label="Province"
          value={selectedProvince}
          onChange={onProvinceChange}
          disabled={disabled}
        >
          <option value="">All provinces</option>
          {provinces.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </SelectField>

        <SelectField
          label="Indicator"
          value={selectedIndicatorId}
          onChange={onIndicatorChange}
          disabled={disabled}
        >
          <option value="">Select indicator…</option>
          {indicators.map((i) => (
            <option key={i.id} value={i.id}>{i.name}</option>
          ))}
        </SelectField>

        <SelectField
          label="Year"
          value={selectedYear}
          onChange={(v) => onYearChange(Number(v))}
          disabled={disabled}
        >
          {AVAILABLE_YEARS.map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </SelectField>
      </div>
    </section>
  )
}
