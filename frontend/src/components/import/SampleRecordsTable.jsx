/**
 * SampleRecordsTable — displays the first 10 valid rows from the preview response.
 *
 * Props
 * ─────
 * records   SampleRecord[]   array of up to 10 sample records from CsvPreviewResponse
 *
 * SampleRecord shape (from backend):
 *   { row_number, province_code, indicator_code, value, reference_year, dataset_name }
 */
export default function SampleRecordsTable({ records }) {
  if (!records || records.length === 0) return null

  return (
    <div className="rounded-xl border border-[var(--sf-border)] bg-slate-800/60 overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--sf-border)] flex items-center justify-between gap-4 flex-wrap">
        <p className="text-[11px] font-semibold uppercase tracking-[var(--sf-tracking-widest)] text-[var(--sf-text-subtle)]">
          Sample Records
        </p>
        <span className="text-xs text-[var(--sf-text-muted)]">
          First {records.length} valid row{records.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Scrollable table — overflow-x-auto for mobile */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-label="Sample import records">
          <thead className="text-[10px] font-semibold uppercase tracking-[var(--sf-tracking-widest)] text-[var(--sf-text-subtle)] bg-slate-900/80 border-b border-[var(--sf-border)]">
            <tr>
              <th scope="col" className="px-4 py-2.5 text-left whitespace-nowrap">Row</th>
              <th scope="col" className="px-4 py-2.5 text-left whitespace-nowrap">Province</th>
              <th scope="col" className="px-4 py-2.5 text-left whitespace-nowrap">Indicator</th>
              <th scope="col" className="px-4 py-2.5 text-right whitespace-nowrap">Value</th>
              <th scope="col" className="px-4 py-2.5 text-right whitespace-nowrap">Year</th>
              <th scope="col" className="px-4 py-2.5 text-left whitespace-nowrap">Dataset</th>
            </tr>
          </thead>
          <tbody>
            {records.map((rec, i) => (
              <tr
                key={i}
                className="border-t border-white/5 hover:bg-white/5 transition-colors duration-150"
              >
                <td className="px-4 py-2 tabular-nums text-[var(--sf-text-muted)] whitespace-nowrap">
                  {rec.row_number}
                </td>
                <td className="px-4 py-2 font-mono text-xs text-[var(--sf-text)] whitespace-nowrap">
                  {rec.province_code}
                </td>
                <td className="px-4 py-2 font-mono text-xs text-[var(--sf-text)] whitespace-nowrap">
                  {rec.indicator_code}
                </td>
                <td className="px-4 py-2 tabular-nums text-right text-[var(--sf-text)] whitespace-nowrap">
                  {rec.value}
                </td>
                <td className="px-4 py-2 tabular-nums text-right text-[var(--sf-text-muted)] whitespace-nowrap">
                  {rec.reference_year}
                </td>
                <td className="px-4 py-2 text-xs text-[var(--sf-text-muted)] max-w-[180px] truncate">
                  {rec.dataset_name}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
