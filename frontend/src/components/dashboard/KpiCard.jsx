/**
 * KpiCard — a single KPI metric card.
 *
 * Props
 * ─────
 * label      {string}        Card heading (e.g. "National Average")
 * value      {string|number} Primary displayed value
 * unit       {string}        Optional unit suffix (e.g. "%")
 * subtitle   {string}        Optional secondary line (e.g. province name)
 * icon       {JSX.Element}   Decorative SVG icon (should carry aria-hidden)
 * variant    {string}        One of: "primary" | "success" | "danger" | "info"
 *                            Defaults to "primary"
 *
 * Accent variants
 * ───────────────
 * primary  → indigo  (National Average)
 * success  → emerald (Highest Province)
 * danger   → rose    (Lowest Province)
 * info     → sky     (Coverage)
 */

const VARIANTS = {
  primary: {
    iconBg:   'bg-indigo-500/15',
    iconText: 'text-indigo-400',
    accent:   'border-l-indigo-500/40',
  },
  success: {
    iconBg:   'bg-emerald-500/15',
    iconText: 'text-emerald-400',
    accent:   'border-l-emerald-500/40',
  },
  danger: {
    iconBg:   'bg-rose-500/15',
    iconText: 'text-rose-400',
    accent:   'border-l-rose-500/40',
  },
  info: {
    iconBg:   'bg-sky-500/15',
    iconText: 'text-sky-400',
    accent:   'border-l-sky-500/40',
  },
}

/**
 * @param {{
 *   label:    string,
 *   value:    string | number,
 *   unit?:    string,
 *   subtitle?: string,
 *   icon?:    import('react').ReactNode,
 *   variant?: 'primary' | 'success' | 'danger' | 'info',
 * }} props
 */
export default function KpiCard({
  label,
  value,
  unit,
  subtitle,
  icon,
  variant = 'primary',
}) {
  const { iconBg, iconText, accent } = VARIANTS[variant] ?? VARIANTS.primary

  return (
    <article
      className={`
        rounded-xl
        border border-[var(--sf-border)]
        border-l-2 ${accent}
        bg-slate-800/60
        p-4 sm:p-5
        shadow-[var(--sf-shadow-card)]
        hover:shadow-[var(--sf-shadow-card-hover)]
        hover:border-[var(--sf-border-hover)]
        transition-all duration-200
        flex flex-col gap-3
      `}
    >
      {/* Icon container */}
      {icon && (
        <div
          className={`
            w-9 h-9 rounded-lg
            ${iconBg} ${iconText}
            flex items-center justify-center
            flex-shrink-0
          `}
        >
          {icon}
        </div>
      )}

      {/* Text block */}
      <div className="min-w-0">
        {/* Label */}
        <p
          className="
            text-[11px] font-medium uppercase
            tracking-[var(--sf-tracking-widest)]
            text-[var(--sf-text-subtle)]
            mb-1
          "
        >
          {label}
        </p>

        {/* Primary value */}
        <p
          className="
            text-[28px] font-bold leading-none
            text-white tabular-nums
            [font-family:var(--sf-font-family)]
          "
        >
          {value ?? '—'}
          {unit && (
            <span className="ml-1.5 text-sm font-normal text-[var(--sf-text-muted)]">
              {unit}
            </span>
          )}
        </p>

        {/* Optional subtitle (e.g. province name for highest/lowest) */}
        {subtitle && (
          <p className="mt-1 text-xs text-[var(--sf-text-muted)] truncate">
            {subtitle}
          </p>
        )}
      </div>
    </article>
  )
}
