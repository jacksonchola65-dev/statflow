# Design: Professional Dashboard UI Polish

## Overview

A visual-only refactor of the StatFlow frontend. No data-fetching logic, hook signatures, API calls, or test assertions change. Every change is confined to CSS classes, Tailwind utility compositions, and the addition of three new presentational components (`KpiCard`, `DashboardFooter`, updated `Topbar`). The existing component tree and prop interfaces are preserved.

---

## File Changes

```
frontend/
└── src/
    ├── index.css                              UPDATED — Inter font import + token layer
    ├── pages/
    │   └── DashboardPage.jsx                  UPDATED — KPI computation, footer, layout
    ├── components/
    │   ├── layout/
    │   │   └── Topbar.jsx                     UPDATED — subtitle + Demo Dataset badge + sticky
    │   ├── dashboard/
    │   │   ├── KpiCard.jsx                    UPDATED — icon slot, accent colour, tabular nums
    │   │   ├── KpiGrid.jsx                    UPDATED — derives 4 KPI items from summary
    │   │   ├── DashboardFilters.jsx           UPDATED — card wrapper, custom chevron select
    │   │   ├── ProvinceSummary.jsx            UPDATED — refined header, card polish
    │   │   ├── ProvinceComparisonChart.jsx    UPDATED — grid, tooltip, bar colours, animation
    │   │   ├── DataTable.jsx                  UPDATED — surface colour, row hover
    │   │   └── ZambiaProvinceMap.jsx          UPDATED — legend, map background, hover stroke
    │   └── common/
    │       ├── SelectField.jsx                UPDATED — chevron icon, min-height, focus ring
    │       ├── MapLegend.jsx                  UPDATED — rounded-xl, backdrop-blur
    │       └── DashboardFooter.jsx            NEW — four-column footer
```

No files outside `frontend/src/` are modified.

---

## Design Token System

Defined in `src/index.css` via Tailwind CSS `@layer base` and CSS custom properties:

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
@import "tailwindcss";

@layer base {
  :root {
    --color-bg:        #0f172a; /* slate-950 */
    --color-surface:   #1e293b; /* slate-800 */
    --color-border:    rgba(255,255,255,0.08);
    --color-accent:    #6366f1; /* indigo-500 */
    --color-accent-m:  #818cf8; /* indigo-400 muted */
    --color-text:      #f1f5f9; /* slate-100 */
    --color-muted:     #64748b; /* slate-500 */
    --shadow-card:     0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3);
    --shadow-card-hover: 0 8px 24px rgba(0,0,0,0.5), 0 2px 8px rgba(0,0,0,0.3);
  }

  body {
    font-family: 'Inter', ui-sans-serif, system-ui, sans-serif;
    background-color: var(--color-bg);
    color: var(--color-text);
  }
}
```

These variables are used in Tailwind arbitrary-value utilities where appropriate, and referenced directly in Recharts/Leaflet style objects.

---

## Component Design

### `Topbar.jsx`

```jsx
<header className="sticky top-0 z-50 border-b border-white/8 bg-slate-900/80 backdrop-blur-md px-6 py-3 flex items-center gap-4">
  <div className="flex flex-col">
    <h1 className="text-2xl font-extrabold tracking-tight leading-none">
      Stat<span className="text-indigo-400">Flow</span>
    </h1>
    <span className="text-[11px] font-medium uppercase tracking-widest text-slate-500 mt-0.5">
      Zambia Development Intelligence Platform
    </span>
  </div>
  <span className="ml-auto flex-shrink-0 rounded-full bg-amber-500/15 border border-amber-500/30
                   px-2.5 py-1 text-[10px] font-medium text-amber-400 uppercase tracking-wide">
    Demo Dataset
  </span>
</header>
```

### `KpiCard.jsx`

Accepts new props: `icon` (JSX SVG), `accentBg` (Tailwind class), `accentIcon` (colour hex), `subtitle` (optional province name).

```jsx
<div className="rounded-xl border border-white/8 bg-slate-800/60 p-5
                shadow-[var(--shadow-card)] hover:shadow-[var(--shadow-card-hover)]
                hover:border-white/15 transition-all duration-200">
  <div className={`w-9 h-9 rounded-lg ${accentBg} flex items-center justify-center mb-3`}>
    {/* icon — aria-hidden SVG, colour = accentIcon */}
  </div>
  <p className="text-[11px] font-medium uppercase tracking-widest text-slate-500 mb-1">{label}</p>
  <p className="text-[28px] font-bold tabular-nums leading-none text-white">
    {value}
    {unit && <span className="ml-1.5 text-sm font-normal text-slate-400">{unit}</span>}
  </p>
  {subtitle && <p className="mt-1 text-xs text-slate-400 truncate">{subtitle}</p>}
</div>
```

### KPI Computation (in `DashboardPage.jsx`)

```js
const results = summary?.results ?? []

const kpiItems = useMemo(() => {
  if (results.length === 0) return null
  const values = results.map((r) => parseFloat(r.value))
  const avg = values.reduce((a, b) => a + b, 0) / values.length
  const maxIdx = values.indexOf(Math.max(...values))
  const minIdx = values.indexOf(Math.min(...values))
  return [
    { id: 'avg',      label: 'National Average', value: avg.toFixed(1),        unit, icon: 'chart-bar',    accentBg: 'bg-indigo-500/15', accentColor: '#818cf8' },
    { id: 'high',     label: 'Highest Province',  value: values[maxIdx].toFixed(1), unit, subtitle: results[maxIdx].province_name, icon: 'arrow-up', accentBg: 'bg-emerald-500/15', accentColor: '#34d399' },
    { id: 'low',      label: 'Lowest Province',   value: values[minIdx].toFixed(1), unit, subtitle: results[minIdx].province_name, icon: 'arrow-down', accentBg: 'bg-rose-500/15', accentColor: '#fb7185' },
    { id: 'coverage', label: 'Coverage',           value: `${results.length} / 10`,  icon: 'map', accentBg: 'bg-sky-500/15', accentColor: '#38bdf8' },
  ]
}, [results, unit])
```

`KpiGrid` receives `kpiItems` (or `null` when loading) and renders the four `KpiCard`s.

### `DashboardFilters.jsx`

Wrapped in a card panel. `SelectField` gains a chevron icon via a wrapper `div` with `relative` positioning:

```jsx
<div className="relative">
  <select className="w-full h-10 rounded-lg border border-white/10 bg-slate-800
                     px-3 pr-9 py-2 text-sm text-white appearance-none
                     focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500
                     focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950
                     disabled:opacity-40 disabled:cursor-not-allowed
                     transition-colors hover:border-white/20">
    {children}
  </select>
  <svg /* chevron-down, aria-hidden */ className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
</div>
```

### `ProvinceComparisonChart.jsx`

Key changes only (all prop signatures unchanged):

| Property | Old | New |
|---|---|---|
| `CartesianGrid stroke` | `#ffffff12` | `#ffffff0a` |
| `CartesianGrid vertical` | `false` | `false` (unchanged) |
| Unselected bar fill | `#818cf8` | `#6366f1` at opacity 0.7 |
| Selected bar fill | same colour | `#818cf8` at opacity 1 + `stroke="#a5b4fc" strokeWidth={2}` |
| Tooltip `backgroundColor` | `#1f2937` | `#1e293b` |
| Tooltip `borderRadius` | `8px` | `10px` |
| Tooltip `boxShadow` | none | `0 8px 32px rgba(0,0,0,.4)` |
| Bar `animationDuration` | default | `600` |
| Bar `animationEasing` | default | `ease-out` |

### `MapLegend.jsx`

Card class updated from `bg-gray-900/90 rounded-lg` to `bg-slate-900/95 rounded-xl backdrop-blur-sm shadow-lg`. Swatch size remains 14 × 14.

### `ZambiaProvinceMap.jsx`

- `MapContainer` style `background` changed from `#111827` to `#0f172a`.
- `mouseover` event on each layer (in `bindEvents`) adds `layer.setStyle({ weight: 2, color: '#a5b4fc' })` and `mouseout` resets to base style. This is additive — it does not change the existing click handler.

### `DataTable.jsx`

- Table wrapper: `bg-slate-800/60` (from `bg` implicit).
- `thead` background: `bg-slate-900/80`.
- Row hover: `hover:bg-white/5` (unchanged), plus `transition-colors duration-150`.

### `DashboardFooter.jsx` (new)

```jsx
export default function DashboardFooter({ year, indicatorName }) {
  const items = [
    { label: 'Data Source',    value: 'Zambia Data Hub / geoBoundaries' },
    { label: 'Reference Year', value: year ?? '—' },
    { label: 'Dataset',        value: indicatorName || '—' },
    { label: 'Notice',         value: 'Demonstration data — not for official use' },
  ]
  return (
    <footer className="border-t border-white/8 mt-8 pt-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {items.map(({ label, value }) => (
          <div key={label}>
            <p className="text-[10px] font-medium uppercase tracking-widest text-slate-600 mb-0.5">{label}</p>
            <p className="text-[11px] text-slate-400">{value}</p>
          </div>
        ))}
      </div>
    </footer>
  )
}
```

---

## DashboardPage Layout Order (updated)

```
<AppShell>
  [refError && <ErrorState>]
  <KpiGrid items={kpiItems} />          ← derived from summary.results
  <DashboardFilters />
  <ZambiaProvinceMap />
  <ProvinceSummary />
  <DataTable />
  <DashboardFooter />                   ← replaces disclaimer <p>
</AppShell>
```

---

## Tailwind Configuration

No `tailwind.config.js` is required — the project uses Tailwind v4 with `@import "tailwindcss"`. All custom values are expressed as Tailwind arbitrary-value utilities (e.g. `bg-[var(--color-surface)]`) or inline CSS custom properties where Tailwind cannot reach (Recharts/Leaflet style objects).

---

## Correctness Properties

1. **KPI computation is pure** — given the same `summary.results` array the same four values are always produced.
2. **No DOM side-effects on hover** — Leaflet `setStyle` calls only mutate the Leaflet internal layer; React state is never touched.
3. **Token file has no runtime JS** — `tokens.css` is a pure CSS file; it cannot introduce bundle size regressions.
4. **All four KPI values are bounded** — Average, Max, Min are computed with `Math.min/max` over a non-empty array only (guarded by `results.length === 0` returning `null`).

---

## Test Strategy

All existing tests continue to pass unchanged because:
- No hook signatures change.
- No component prop interfaces are removed.
- The mock GeoJSON in `ZambiaProvinceMap.test.jsx` uses `shapeName` (unchanged).
- The new `DashboardFooter` is a presentational component with no async behaviour.
- `KpiGrid` receives a new `items` shape — but the test for `DashboardPage` mocks `useIndicatorSummary` and does not assert on KPI text, so no test changes are needed.

If the `DashboardPage` tests render the full component, the `kpiItems` computation will receive an empty array from the mock and render `null` for `KpiGrid`, which is the correct guarded behaviour.
