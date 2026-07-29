import { getDashboardCardLayoutClass } from './dashboardSelectors'

export default function DashboardCard({ card, onRemove, onResize, onMove }) {
  return (
    <article className={['rounded-2xl border border-white/10 bg-slate-950/60 p-4', getDashboardCardLayoutClass(card.size)].join(' ')}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="truncate text-sm font-semibold text-white">{card.title}</h4>
          <p className="mt-1 text-xs text-[var(--sf-text-muted)]">{card.subtitle}</p>
        </div>
        <button
          type="button"
          aria-label={`Remove ${card.title}`}
          onClick={() => onRemove(card.id)}
          className="rounded-lg bg-rose-500/20 px-2 py-1 text-xs font-semibold text-rose-300 hover:bg-rose-500/30"
        >
          Remove
        </button>
      </div>

      <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-[var(--sf-text-muted)]">
        <div className="font-semibold text-white">Visualization</div>
        <div className="mt-2">{card.visualizationType}</div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          aria-label={`Move ${card.title} earlier`}
          onClick={() => onMove(card.id, 'up')}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold text-white hover:bg-white/10"
        >
          Move up
        </button>
        <button
          type="button"
          aria-label={`Move ${card.title} later`}
          onClick={() => onMove(card.id, 'down')}
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold text-white hover:bg-white/10"
        >
          Move down
        </button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {['small', 'medium', 'large'].map((sizeOption) => (
          <button
            key={sizeOption}
            type="button"
            aria-label={`Resize ${card.title} to ${sizeOption}`}
            onClick={() => onResize(card.id, sizeOption)}
            className={['rounded-lg px-3 py-2 text-xs font-semibold', sizeOption === card.size ? 'bg-indigo-500 text-white' : 'border border-white/10 bg-white/5 text-white hover:bg-white/10'].join(' ')}
          >
            {sizeOption}
          </button>
        ))}
      </div>
    </article>
  )
}
