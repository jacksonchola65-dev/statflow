import DashboardCard from './DashboardCard'

export default function DashboardGrid({ dashboard, onRemove, onResize, onMove, previewMode = false }) {
  if (!dashboard || !Array.isArray(dashboard.cards) || dashboard.cards.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-8 text-sm text-[var(--sf-text-muted)]">
        Add a visualization to start building the dashboard.
      </div>
    )
  }

  return (
    <section aria-label="Dashboard grid" className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {dashboard.cards.map((card) => (
        <DashboardCard
          key={card.id}
          card={card}
          onRemove={onRemove}
          onResize={onResize}
          onMove={onMove}
          previewMode={previewMode}
        />
      ))}
    </section>
  )
}
