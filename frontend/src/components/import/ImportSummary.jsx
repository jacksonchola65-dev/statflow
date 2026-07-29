/**
 * ImportSummary — validation count badges for the preview state.
 *
 * Props
 * ─────
 * preview  object  the CsvPreviewResponse from the backend
 */
export default function ImportSummary({ preview }) {
  const items = [
    { label: 'Total rows',     value: preview.total_rows,    variant: 'neutral' },
    { label: 'Valid',          value: preview.valid_rows,    variant: 'success' },
    { label: 'Invalid',        value: preview.invalid_rows,  variant: preview.invalid_rows > 0 ? 'danger' : 'neutral' },
    { label: 'Duplicates',     value: preview.duplicate_rows, variant: preview.duplicate_rows > 0 ? 'warning' : 'neutral' },
    { label: 'Conflicts',      value: preview.conflict_rows,  variant: preview.conflict_rows > 0 ? 'danger' : 'neutral' },
  ]

  const variantClasses = {
    neutral: 'bg-slate-700/60 text-[var(--sf-text-muted)]',
    success: 'bg-emerald-500/15 text-emerald-400',
    danger:  'bg-rose-500/15 text-rose-400',
    warning: 'bg-amber-500/15 text-amber-400',
  }

  return (
    <div
      className="rounded-xl border border-[var(--sf-border)] bg-slate-800/60 p-4 sm:p-5"
      aria-label="Import validation summary"
    >
      <p className="text-[11px] font-semibold uppercase tracking-[var(--sf-tracking-widest)] text-[var(--sf-text-subtle)] mb-3">
        Validation Summary
      </p>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {items.map(({ label, value, variant }) => (
          <div
            key={label}
            className={`rounded-lg px-3 py-2.5 text-center ${variantClasses[variant]}`}
          >
            <p className="text-[22px] font-bold tabular-nums leading-none">{value}</p>
            <p className="text-[11px] font-medium mt-1 opacity-80">{label}</p>
          </div>
        ))}
      </div>

      {/* can_confirm status */}
      <div className={`mt-4 flex items-center gap-2 text-sm ${preview.can_confirm ? 'text-emerald-400' : 'text-[var(--sf-text-subtle)]'}`}>
        <svg aria-hidden="true" className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
          {preview.can_confirm ? (
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
          ) : (
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
          )}
        </svg>
        {preview.can_confirm
          ? 'All rows are valid — ready to import.'
          : 'Fix the issues above before confirming.'}
      </div>
    </div>
  )
}
