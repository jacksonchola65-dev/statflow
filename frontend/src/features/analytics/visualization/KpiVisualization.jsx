import { formatVisualizationValue } from './visualizationRules'

export default function KpiVisualization({ data }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {data.map((item) => (
        <article key={item.key} className="rounded-2xl border border-white/10 bg-white/5 p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--sf-text-muted)]">{item.label}</p>
          <p className="mt-3 text-3xl font-semibold text-white tabular-nums">{formatVisualizationValue(item.value)}</p>
        </article>
      ))}
    </div>
  )
}
