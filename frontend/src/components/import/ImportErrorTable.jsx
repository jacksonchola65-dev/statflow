/**
 * ImportErrorTable — displays row-level validation errors.
 *
 * Props
 * ─────
 * errors            RowError[]   array of error objects (max 100)
 * totalErrorCount   number       true total (may exceed 100)
 * errorsT runcated  boolean      whether the list is truncated
 */
export default function ImportErrorTable({ errors, totalErrorCount, errorsTruncated }) {
  if (!errors || errors.length === 0) return null

  return (
    <div className="rounded-xl border border-rose-500/30 bg-slate-800/60 overflow-hidden">
      <div className="px-4 py-3 border-b border-rose-500/20 flex items-center justify-between gap-4 flex-wrap">
        <p className="text-[11px] font-semibold uppercase tracking-[var(--sf-tracking-widest)] text-rose-400">
          Validation Errors
        </p>
        <span className="text-xs text-[var(--sf-text-muted)]">
          {totalErrorCount} error{totalErrorCount !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Truncation notice */}
      {errorsTruncated && (
        <p
          role="status"
          className="px-4 py-2 text-xs text-amber-400 bg-amber-500/8 border-b border-amber-500/20"
        >
          Showing the first 100 of {totalErrorCount} validation errors.
        </p>
      )}

      {/* Scrollable table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-label="Validation error details">
          <thead className="text-[10px] font-semibold uppercase tracking-[var(--sf-tracking-widest)] text-[var(--sf-text-subtle)] bg-slate-900/80 border-b border-[var(--sf-border)]">
            <tr>
              <th scope="col" className="px-4 py-2.5 text-left whitespace-nowrap">Row</th>
              <th scope="col" className="px-4 py-2.5 text-left whitespace-nowrap">Column</th>
              <th scope="col" className="px-4 py-2.5 text-left whitespace-nowrap">Value</th>
              <th scope="col" className="px-4 py-2.5 text-left">Message</th>
            </tr>
          </thead>
          <tbody>
            {errors.map((err, i) => (
              <tr
                key={i}
                className="border-t border-white/5 hover:bg-white/5 transition-colors duration-150"
              >
                <td className="px-4 py-2 tabular-nums text-[var(--sf-text-muted)] whitespace-nowrap">{err.row_number}</td>
                <td className="px-4 py-2 font-mono text-xs text-[var(--sf-text-muted)] whitespace-nowrap">{err.column}</td>
                <td className="px-4 py-2 font-mono text-xs text-[var(--sf-text-muted)] max-w-[140px] truncate">
                  {err.raw_value === '' ? <span className="italic opacity-50">(blank)</span> : err.raw_value}
                </td>
                <td className="px-4 py-2 text-xs text-rose-300">{err.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
