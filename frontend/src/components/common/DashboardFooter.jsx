/**
 * DashboardFooter — professional four-item contextual footer.
 *
 * Displays:
 *  - Data Source
 *  - Reference Year   (driven by selectedYear prop)
 *  - Dataset          (driven by indicatorName prop)
 *  - Notice           (static demonstration-data disclaimer)
 *
 * Layout:
 *  - 2 columns on xs (< 640 px)
 *  - 4 columns on sm+ (≥ 640 px)
 *
 * Uses design tokens from src/index.css.
 *
 * @param {{
 *   year?:          number | string,
 *   indicatorName?: string,
 * }} props
 */
export default function DashboardFooter({ year, indicatorName }) {
  const items = [
    {
      label: 'Data Source',
      value: 'Zambia Data Hub / geoBoundaries',
    },
    {
      label: 'Reference Year',
      value: year ?? '—',
    },
    {
      label: 'Dataset',
      value: indicatorName || '—',
    },
    {
      label: 'Notice',
      value: 'Demonstration data — not official statistics.',
    },
  ]

  return (
    <footer
      className="
        border-t border-[var(--sf-border)]
        mt-8 pt-6
      "
      aria-label="Dashboard metadata"
    >
      <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
        {items.map(({ label, value }) => (
          <div key={label}>
            <p
              className="
                text-[10px] font-semibold uppercase
                tracking-[var(--sf-tracking-widest)]
                text-[var(--sf-text-disabled)]
                mb-0.5
              "
            >
              {label}
            </p>
            <p className="text-[11px] text-[var(--sf-text-subtle)] leading-snug">
              {value}
            </p>
          </div>
        ))}
      </div>
    </footer>
  )
}
