import { PALETTE, NO_DATA_COLOR } from '../../utils/choropleth'

/**
 * MapLegend — polished five-level choropleth legend with "No data" swatch.
 *
 * Visual changes from previous version:
 *  - Panel: bg-slate-900/95 rounded-xl backdrop-blur-sm shadow-lg
 *    (was bg-gray-900/90 rounded-lg — no blur, no shadow)
 *  - Border: border-[var(--sf-border)] (was border-white/10 — same value, now token)
 *  - Legend label: token typography — 10px, slate-500
 *  - Swatches: 14×14 px rounded-sm (was 16×16 w-4 h-4)
 *  - Range text: text-[var(--sf-text-muted)] for better legibility
 *  - No-data text: text-[var(--sf-text-subtle)]
 *  - min-width increased to 148 px
 *
 * All prop signatures and choropleth logic are unchanged.
 *
 * @param {{
 *   bins: number[],
 *   unit: string,
 * }} props
 */
export default function MapLegend({ bins, unit }) {
  return (
    <div
      className="
        bg-slate-900/95
        border border-[var(--sf-border)]
        rounded-xl
        backdrop-blur-sm
        shadow-[var(--sf-shadow-overlay)]
        p-3
        text-xs
        text-[var(--sf-text-muted)]
        min-w-[148px]
      "
      aria-label="Map colour legend"
    >
      {/* Legend header */}
      <p
        className="
          text-[10px] font-semibold uppercase
          tracking-[var(--sf-tracking-widest)]
          text-[var(--sf-text-subtle)]
          mb-2
        "
      >
        {unit ? `Legend (${unit})` : 'Legend'}
      </p>

      {bins.length === 5 ? (
        <ul className="space-y-1.5">
          {PALETTE.map((colour, i) => {
            const low  = i === 0 ? 0 : bins[i - 1]
            const high = bins[i]
            return (
              <li key={colour} className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="
                    inline-block flex-shrink-0
                    w-3.5 h-3.5
                    rounded-sm
                    border border-white/10
                  "
                  style={{ backgroundColor: colour }}
                />
                <span className="text-[var(--sf-text-muted)] text-[11px]">
                  {i === 0
                    ? `≤ ${high.toLocaleString()}`
                    : `${low.toLocaleString()} – ${high.toLocaleString()}`}
                </span>
              </li>
            )
          })}

          {/* No-data swatch */}
          <li className="flex items-center gap-2 mt-0.5 pt-1.5 border-t border-white/8">
            <span
              aria-hidden="true"
              className="
                inline-block flex-shrink-0
                w-3.5 h-3.5
                rounded-sm
                border border-white/10
              "
              style={{ backgroundColor: NO_DATA_COLOR }}
            />
            <span className="text-[var(--sf-text-subtle)] text-[11px]">No data</span>
          </li>
        </ul>
      ) : (
        /* bins not yet computed — show only the no-data swatch */
        <ul className="space-y-1.5">
          <li className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="
                inline-block flex-shrink-0
                w-3.5 h-3.5
                rounded-sm
                border border-white/10
              "
              style={{ backgroundColor: NO_DATA_COLOR }}
            />
            <span className="text-[var(--sf-text-subtle)] text-[11px]">No data</span>
          </li>
        </ul>
      )}
    </div>
  )
}
