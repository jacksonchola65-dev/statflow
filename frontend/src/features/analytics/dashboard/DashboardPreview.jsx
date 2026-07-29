export default function DashboardPreview({ dashboard }) {
  if (!dashboard || !Array.isArray(dashboard.cards) || dashboard.cards.length === 0) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-sm text-[var(--sf-text-muted)]">
        No dashboard preview is available yet.
      </div>
    )
  }

  return (
    <section className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <h3 className="text-base font-semibold text-white">Dashboard preview</h3>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {dashboard.cards.map((card) => (
          <article key={card.id} className="rounded-2xl border border-white/10 bg-slate-900/70 p-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h4 className="text-sm font-semibold text-white">{card.title}</h4>
                <p className="text-xs text-[var(--sf-text-muted)]">{card.subtitle}</p>
              </div>
              <span className="rounded-full bg-white/5 px-2 py-1 text-[11px] uppercase tracking-[0.22em] text-[var(--sf-text-muted)]">
                {card.size}
              </span>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
