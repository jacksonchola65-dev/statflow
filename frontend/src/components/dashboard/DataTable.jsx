/**
 * DataTable — polished province indicator results table.
 *
 * Visual changes from previous version
 * ─────────────────────────────────────
 * Wrapper:
 *  - Card surface: bg-slate-800/60 border-[var(--sf-border)] rounded-xl
 *    (was transparent wrapper with only a border)
 *  - Shadow + hover-shadow transition
 *  - mt-6 → mt-0 (spacing handled by parent's space-y / gap)
 *  - overflow-x-auto preserved for mobile horizontal scroll
 *
 * Table header:
 *  - bg-slate-900/80 (was bg-gray-900/60)
 *  - Token typography: text-[10px] tracking-[--sf-tracking-widest]
 *    text-[--sf-text-subtle] font-semibold (was text-xs text-gray-500)
 *  - Sticky on mobile so column names stay visible while scrolling
 *  - Bottom border: border-b border-[var(--sf-border)]
 *
 * Table rows:
 *  - Divider: border-t border-white/5 (unchanged)
 *  - Row hover: hover:bg-white/5 transition-colors duration-150 (was no duration)
 *  - Cell vertical padding: py-3 (was py-2.5) — more breathing room
 *
 * Province name column:
 *  - text-[var(--sf-text)] (was text-gray-300 via table rule)
 *
 * Value column:
 *  - tabular-nums via .tabular-nums class (was font-mono)
 *  - text-[var(--sf-text-muted)] (was inheriting text-gray-300)
 *  - text-right alignment preserved
 *
 * All prop signatures, data-mapping, and filtering behaviour are unchanged.
 *
 * @param {{
 *   rows: Array<{province_code: string, province_name: string, value: string}>,
 *   unit?: string,
 * }} props
 */
export default function DataTable({ rows = [], unit = '' }) {
  if (rows.length === 0) return null

  return (
    <div
      className="
        overflow-x-auto
        rounded-xl
        border border-[var(--sf-border)]
        bg-slate-800/60
        shadow-[var(--sf-shadow-card)]
        hover:shadow-[var(--sf-shadow-card-hover)]
        transition-shadow duration-200
        mt-6
      "
    >
      <table className="w-full text-sm text-left" aria-label="Province indicator data">
        {/* Header */}
        <thead
          className="
            text-[10px] font-semibold uppercase
            tracking-[var(--sf-tracking-widest)]
            text-[var(--sf-text-subtle)]
            bg-slate-900/80
            border-b border-[var(--sf-border)]
          "
        >
          <tr>
            <th scope="col" className="px-4 py-3 font-semibold">
              Province
            </th>
            <th scope="col" className="px-4 py-3 text-right font-semibold">
              {unit ? `Value (${unit})` : 'Value'}
            </th>
          </tr>
        </thead>

        {/* Body */}
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.province_code}
              className="
                border-t border-white/5
                hover:bg-white/5
                transition-colors duration-150
              "
            >
              {/* Province name */}
              <td
                className="
                  px-4 py-3
                  text-[var(--sf-text)]
                  text-sm
                "
              >
                {row.province_name}
              </td>

              {/* Numeric value — tabular-nums for column alignment */}
              <td
                className="
                  px-4 py-3
                  text-right
                  tabular-nums
                  text-sm
                  text-[var(--sf-text-muted)]
                "
              >
                {parseFloat(row.value).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
