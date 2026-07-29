# Implementation Plan: Professional Dashboard UI Polish

## Overview

Apply a cohesive design system to the StatFlow frontend — typography, spacing, colour tokens, cards, controls, charts, map, KPI cards, header, and footer — without changing any functionality, API calls, or test assertions.

## Tasks

- [x] 1. Establish design tokens and load Inter font
  - Add `@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap')` to `frontend/src/index.css`
  - Add `@layer base` block to `index.css` defining CSS custom properties: `--color-bg`, `--color-surface`, `--color-border`, `--color-accent`, `--color-accent-m`, `--color-text`, `--color-muted`, `--shadow-card`, `--shadow-card-hover`
  - Set `body { font-family: 'Inter', ... }` in the base layer
  - Set `background-color: var(--color-bg)` on `body`
  - References: REQ-2.1 – REQ-2.5, REQ-3.1
  - Acceptance: Inter renders in the browser; CSS variables resolve correctly in DevTools

- [x] 2. Polish the Topbar
  - Update `frontend/src/components/layout/Topbar.jsx`
  - Make the header `sticky top-0 z-50` with `bg-slate-900/80 backdrop-blur-md`
  - Add the subtitle "Zambia Development Intelligence Platform" (11 px, uppercase, slate-500)
  - Add the "Demo Dataset" amber pill badge aligned to the right
  - References: REQ-6.1 – REQ-6.5
  - Acceptance: Topbar sticks on scroll; badge and subtitle visible; all existing text preserved

- [x] 3. Update KpiCard and KpiGrid with icon slot and accent colours
  - Update `frontend/src/components/dashboard/KpiCard.jsx`
    - Accept new props: `icon` (JSX), `accentBg` (string), `accentColor` (hex string), `subtitle` (optional string)
    - Add icon container: `w-9 h-9 rounded-lg {accentBg} flex items-center justify-center mb-3`
    - Change value font to `text-[28px] font-bold tabular-nums`
    - Add card hover shadow transition: `hover:shadow-[var(--shadow-card-hover)] transition-all duration-200`
    - Add `subtitle` rendering below value
  - Update `frontend/src/components/dashboard/KpiGrid.jsx`
    - Accept `items` array that may be `null`; render `null` when `items` is null or empty
  - References: REQ-7.1 – REQ-7.5
  - Acceptance: Cards show icons and accent backgrounds; no visual regressions in existing tests

- [x] 4. Compute KPI values in DashboardPage and wire to KpiGrid
  - Update `frontend/src/pages/DashboardPage.jsx`
  - Add `useMemo` that derives `kpiItems` (National Average, Highest Province, Lowest Province, Coverage) from `summary?.results`
  - Define inline SVG icons for each KPI (bar-chart, arrow-up, arrow-down, map-pin)
  - Render `<KpiGrid items={kpiItems} />` as the first section inside `<AppShell>`
  - References: REQ-7.1 – REQ-7.5
  - Acceptance: Four KPI cards display correct computed values when data is loaded; show `—` when loading or empty

- [x] 5. Polish DashboardFilters
  - Update `frontend/src/components/dashboard/DashboardFilters.jsx`
    - Wrap the section in a card panel: `rounded-xl border border-white/8 bg-slate-800/60 p-4 sm:p-6 mb-6`
  - Update `frontend/src/components/common/SelectField.jsx`
    - Add `appearance-none` to `<select>`
    - Set minimum height `h-10`
    - Add chevron-down SVG icon (aria-hidden) in a `relative`/`absolute` wrapper
    - Update focus styles to `focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950`
    - Update disabled to `disabled:opacity-40`
  - References: REQ-8.1 – REQ-8.6
  - Acceptance: Chevron visible on all selects; focus ring appears on keyboard navigation; disabled opacity correct

- [x] 6. Polish the bar chart
  - Update `frontend/src/components/dashboard/ProvinceComparisonChart.jsx`
  - Update `CartesianGrid` stroke to `#ffffff0a`
  - Change unselected bar fill to `#6366f1` at `fillOpacity={0.7}`; selected bar to `#818cf8` at `fillOpacity={1}` with `stroke="#a5b4fc" strokeWidth={2}`
  - Update `Tooltip` contentStyle: `backgroundColor: '#1e293b'`, `borderRadius: '10px'`, `boxShadow: '0 8px 32px rgba(0,0,0,0.4)'`
  - Set `animationDuration={600}` and `animationEasing="ease-out"` on the `<Bar>`
  - References: REQ-9.1 – REQ-9.5
  - Acceptance: Chart renders without errors; selected bar visually distinct; tooltip has new shadow

- [x] 7. Polish the choropleth map and legend
  - Update `frontend/src/components/dashboard/ZambiaProvinceMap.jsx`
    - Change `MapContainer` style `background` to `#0f172a`
    - In `bindEvents`, add `mouseover` → `layer.setStyle({ weight: 2, color: '#a5b4fc' })` and `mouseout` → `layer.setStyle(styleFeature(feature))`
  - Update `frontend/src/components/common/MapLegend.jsx`
    - Change card classes to `bg-slate-900/95 rounded-xl backdrop-blur-sm shadow-lg border border-white/10`
  - References: REQ-10.1 – REQ-10.5
  - Acceptance: Map background matches page; province highlights on hover; legend panel has updated styling

- [x] 8. Polish ProvinceSummary and DataTable cards
  - Update `frontend/src/components/dashboard/ProvinceSummary.jsx`
    - Change outer card bg to `bg-slate-800/60`, add hover shadow transition
  - Update `frontend/src/components/dashboard/DataTable.jsx`
    - Change wrapper to `bg-slate-800/60`
    - Change `thead` bg to `bg-slate-900/80`
    - Add `transition-colors duration-150` to row hover
  - References: REQ-5.1 – REQ-5.3
  - Acceptance: Cards use updated surface colour; row hover transition visible

- [x] 9. Create DashboardFooter and wire into DashboardPage
  - Create `frontend/src/components/common/DashboardFooter.jsx`
    - Props: `year`, `indicatorName`
    - Four-item grid: Data Source, Reference Year, Dataset, Notice
    - Styling: `border-t border-white/8 mt-8 pt-6`, 2-col on mobile / 4-col on sm+
    - Label: 10 px uppercase tracking-widest slate-600; value: 11 px slate-400
  - Update `frontend/src/pages/DashboardPage.jsx`
    - Remove the existing `<p className="mt-4 text-center text-xs text-gray-600">` disclaimer
    - Add `<DashboardFooter year={selectedYear} indicatorName={selectedIndicator?.name} />` as the last child of `<AppShell>`
  - References: REQ-11.1 – REQ-11.5
  - Acceptance: Footer renders below data table; disclaimer paragraph no longer present; reference year and indicator name update when filters change

- [x] 10. Verify all quality gates
  - Run `node node_modules/vitest/vitest.mjs run` — all 47 tests pass
  - Run `node node_modules/oxlint/dist/cli.js src` — exit code 0, no errors
  - Visually verify in browser at 375 px, 768 px, and 1280 px:
    - Inter font loads
    - Topbar is sticky and shows subtitle + badge
    - Four KPI cards show correct values
    - Filters card renders with chevrons and correct focus ring
    - Bar chart has updated colours and tooltip shadow
    - Map hover highlights in indigo, selected in orange
    - Footer shows correct year and indicator name
  - References: REQ-1.1 – REQ-1.5, REQ-12.1 – REQ-12.5
  - Acceptance: All automated checks pass; no visual regressions observed

## Task Dependency Graph

```
1 (tokens + font)
    │
    ├──► 2 (Topbar)
    │
    ├──► 3 (KpiCard + KpiGrid)
    │         │
    │         └──► 4 (KPI computation in DashboardPage)
    │
    ├──► 5 (DashboardFilters + SelectField)
    │
    ├──► 6 (bar chart)
    │
    ├──► 7 (map + legend)
    │
    ├──► 8 (ProvinceSummary + DataTable cards)
    │
    └──► 9 (DashboardFooter)
              │
              └──► 10 (quality gates)
```

Tasks 2 – 9 can be executed in parallel once Task 1 is complete. Task 10 must run last.

## Notes

- All icons are inline SVG (no new npm packages).
- Tailwind arbitrary-value utilities (`bg-[var(--color-surface)]`) are used where CSS variables are needed inside Tailwind classes.
- Recharts and Leaflet style objects reference hex literals directly; they do not read from CSS variables.
- The KPI computation is pure and guarded — it produces `null` when `summary.results` is empty, causing `KpiGrid` to render nothing during loading, which is the correct behaviour for existing tests.
