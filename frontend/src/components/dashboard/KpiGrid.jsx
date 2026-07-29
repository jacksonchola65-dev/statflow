import KpiCard from './KpiCard'

/**
 * KpiGrid — responsive 1 / 2 / 4 column grid of KpiCards.
 *
 * Props
 * ─────
 * items   {Array | null}   Array of KpiCard prop objects, or null/[] to render nothing.
 *                          Each item may include: label, value, unit, subtitle, icon, variant.
 *
 * Column behaviour
 * ────────────────
 * xs  (< 640 px)   → 1 column
 * sm  (≥ 640 px)   → 2 columns
 * lg  (≥ 1024 px)  → 4 columns
 *
 * @param {{
 *   items: Array<{
 *     label:    string,
 *     value:    string | number,
 *     unit?:    string,
 *     subtitle?: string,
 *     icon?:    import('react').ReactNode,
 *     variant?: 'primary' | 'success' | 'danger' | 'info',
 *   }> | null
 * }} props
 */
export default function KpiGrid({ items = [] }) {
  if (!items || items.length === 0) return null

  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6"
      role="region"
      aria-label="Key performance indicators"
    >
      {items.map((item) => (
        <KpiCard key={item.label} {...item} />
      ))}
    </div>
  )
}
