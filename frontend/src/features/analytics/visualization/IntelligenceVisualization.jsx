import AnalyticsVisualization from './AnalyticsVisualization'

export default function IntelligenceVisualization({ artifact }) {
  const dimension = artifact.dimension?.column
  const measure = artifact.measure?.column
  const columns = []
  if (dimension) columns.push({ identifier: dimension, label: artifact.dimension.label, data_type: 'text', role: 'dimension', dimension_eligible: true })
  if (measure) columns.push({ identifier: 'value', label: measure, data_type: 'decimal', role: 'measure', measure_eligible: true })

  if (artifact.type === 'table') {
    const headers = artifact.data.length ? Object.keys(artifact.data[0]) : []
    return (
      <div className="overflow-x-auto rounded-xl border border-white/10">
        <table className="min-w-full text-left text-sm" aria-label={artifact.title}>
          <thead className="bg-white/5 text-xs uppercase text-[var(--sf-text-muted)]"><tr>{headers.map((header) => <th className="px-3 py-2" key={header}>{header}</th>)}</tr></thead>
          <tbody>{artifact.data.map((row, index) => <tr className="border-t border-white/10" key={index}>{headers.map((header) => <td className="px-3 py-2 text-white" key={header}>{String(row[header] ?? '—')}</td>)}</tr>)}</tbody>
        </table>
      </div>
    )
  }

  const rows = artifact.data.map((row) => ({ ...(dimension ? { [dimension]: row[dimension] } : {}), value: row.value }))
  return <AnalyticsVisualization result={{ columns, rows, row_count: rows.length }} chartType={artifact.type} />
}
