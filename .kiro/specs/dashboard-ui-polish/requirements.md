# Requirements: Professional Dashboard UI Polish

## Overview

Transform the existing StatFlow dashboard into a professional government / business-intelligence interface by applying a cohesive design system across every visual layer — typography, spacing, colour, cards, controls, charts, and map. No existing functionality is changed, no backend APIs are modified, and no new features are introduced.

---

## Requirements

### REQ-1: Functional Preservation

- **REQ-1.1** Every existing filter (Province, Indicator, Year) must continue to work exactly as it does today.
- **REQ-1.2** The choropleth map must continue to load GeoJSON, colour provinces, show tooltips, support click-to-select, and deselect on second click.
- **REQ-1.3** The bar chart must continue to render province values and highlight the selected province.
- **REQ-1.4** The data table must continue to display all rows and update when the province filter changes.
- **REQ-1.5** All existing tests must pass without modification after every visual change.
- **REQ-1.6** No backend API calls are added, removed, or changed.

---

### REQ-2: Design System — Tokens

- **REQ-2.1** A single source-of-truth CSS custom-property token file (`src/styles/tokens.css`) defines all design tokens: colours, spacing, radii, shadows, and typography scales.
- **REQ-2.2** The spacing scale is based on an 8 px base unit (4, 8, 12, 16, 24, 32, 48, 64 px).
- **REQ-2.3** The colour palette uses a slate/gray dark base (`#0f172a` page background, `#1e293b` card surface) with an indigo accent (`#6366f1` primary, `#818cf8` muted accent).
- **REQ-2.4** Border radii use `rounded-xl` (12 px) for cards and panels, `rounded-lg` (8 px) for inputs and small elements.
- **REQ-2.5** Shadows use a two-level scale: `shadow-card` (subtle, dark-mode-safe) for resting cards and `shadow-card-hover` (elevated) for hovered cards.

---

### REQ-3: Typography

- **REQ-3.1** The Inter font (Google Fonts) is loaded as the primary sans-serif typeface via `@import` in `index.css`.
- **REQ-3.2** Heading hierarchy:
  - H1 (app title): 24 px, font-weight 800, tracking-tight
  - H2 (section title): 18 px, font-weight 600
  - H3 (card label): 11 px, font-weight 500, uppercase, letter-spacing 0.08em, muted colour
- **REQ-3.3** Body text is 14 px, font-weight 400, colour `text-slate-300`.
- **REQ-3.4** Secondary / muted text is 12 px, colour `text-slate-500`.
- **REQ-3.5** Numeric values in KPI cards are 28 px, font-weight 700, `font-variant-numeric: tabular-nums`.

---

### REQ-4: Layout and Spacing

- **REQ-4.1** The page background is `#0f172a` (slate-950).
- **REQ-4.2** The main content area has horizontal padding of 24 px on mobile and 32 px on desktop (`px-6 lg:px-8`), and vertical padding of 32 px (`py-8`).
- **REQ-4.3** Vertical gap between dashboard sections is 24 px (`gap-6` / `space-y-6`).
- **REQ-4.4** Cards have internal padding of 24 px on desktop and 16 px on mobile (`p-4 sm:p-6`).
- **REQ-4.5** The KPI grid uses a 4-column layout on ≥ sm breakpoint and a 2-column layout on xs.

---

### REQ-5: Cards

- **REQ-5.1** All card panels use: `rounded-xl border border-white/8 bg-slate-800/60 backdrop-blur-sm`.
- **REQ-5.2** Cards have a resting box-shadow and transition to an elevated box-shadow on hover over 200 ms.
- **REQ-5.3** No card changes its size or content on hover — only shadow and border opacity change.

---

### REQ-6: Dashboard Header (Topbar)

- **REQ-6.1** The Topbar displays the logo text "Stat**Flow**" in white/indigo as today.
- **REQ-6.2** Below or beside the logo, a subtitle reads: **"Zambia Development Intelligence Platform"** in muted slate text (12 px, uppercase, tracking-widest).
- **REQ-6.3** A small pill badge reading **"Demo Dataset"** appears to the right of the subtitle, styled with `bg-amber-500/15 text-amber-400 border border-amber-500/30 rounded-full px-2 py-0.5 text-[10px] font-medium`.
- **REQ-6.4** The Topbar has a bottom border `border-b border-white/8` and a `bg-slate-900/80 backdrop-blur-md` background so it reads as a floating nav bar.
- **REQ-6.5** The Topbar is sticky (`position: sticky; top: 0; z-index: 50`) on all viewport sizes.

---

### REQ-7: KPI Cards

- **REQ-7.1** The `KpiGrid` renders exactly four cards derived from the current analytics results: **National Average**, **Highest Province**, **Lowest Province**, and **Coverage**.
- **REQ-7.2** Each `KpiCard` displays:
  - An SVG icon (24 × 24) in an accent-coloured rounded square background
  - A label (H3 style)
  - A primary value (28 px tabular numeric)
  - An optional unit string
- **REQ-7.3** The four cards use distinct accent colours:
  - National Average: indigo (`#6366f1` background at 15 % opacity, `#818cf8` icon)
  - Highest Province: emerald (`#10b981` at 15 %, `#34d399` icon)
  - Lowest Province: rose (`#f43f5e` at 15 %, `#fb7185` icon)
  - Coverage: sky (`#0ea5e9` at 15 %, `#38bdf8` icon)
- **REQ-7.4** KPI values are computed client-side from `summary.results` inside `DashboardPage` — no new API calls.
  - National Average = mean of all province values (formatted to 1 decimal place)
  - Highest Province = max value with province name as a subtitle
  - Lowest Province = min value with province name as a subtitle
  - Coverage = count of provinces with data / 10, expressed as "N / 10"
- **REQ-7.5** When `summary.results` is empty or loading, KPI cards show `—` as the value.

---

### REQ-8: Dashboard Filters

- **REQ-8.1** The filters container renders as a card panel (`rounded-xl border border-white/8 bg-slate-800/60 p-4 sm:p-6 mb-6`).
- **REQ-8.2** Each `SelectField` label uses H3 typography.
- **REQ-8.3** Each `<select>` element has a minimum height of 40 px, consistent with the 8 px grid.
- **REQ-8.4** The select element uses `appearance-none` with a custom chevron SVG icon positioned at the right edge.
- **REQ-8.5** Focus state shows a 2 px `ring-indigo-500` outline with a 2 px offset, visible in both keyboard and mouse interaction (`:focus-visible`).
- **REQ-8.6** Disabled state reduces opacity to 40 % and changes cursor to `not-allowed`.

---

### REQ-9: Bar Chart

- **REQ-9.1** `CartesianGrid` uses `stroke="#ffffff0a"` (near-invisible horizontal lines, no vertical lines).
- **REQ-9.2** Bar fill uses the indigo palette: unselected bars `#6366f1` at 70 % opacity; the selected province bar `#818cf8` at 100 % with a `2px #a5b4fc` stroke.
- **REQ-9.3** The Recharts `Tooltip` panel uses:
  - `backgroundColor: '#1e293b'`
  - `border: '1px solid rgba(255,255,255,0.1)'`
  - `borderRadius: '10px'`
  - `boxShadow: '0 8px 32px rgba(0,0,0,0.4)'`
  - 13 px font, `color: '#f1f5f9'`
- **REQ-9.4** Bar enter animation uses `isAnimationActive={true}` with `animationDuration={600}` and `animationEasing="ease-out"`.
- **REQ-9.5** X-axis tick labels show the province code; Y-axis tick labels use the existing K/M abbreviation formatter.

---

### REQ-10: Choropleth Map

- **REQ-10.1** The map legend panel uses: `bg-slate-900/95 border border-white/10 rounded-xl p-3 shadow-lg backdrop-blur-sm`.
- **REQ-10.2** Legend colour swatches are 14 × 14 px `rounded-sm` with a `border border-white/10`.
- **REQ-10.3** On province hover, the Leaflet layer applies a `weight: 2, color: '#a5b4fc'` stroke transition over 150 ms (via `mouseover` / `mouseout` handlers already present).
- **REQ-10.4** The selected province renders `weight: 2, color: '#f97316'` stroke (unchanged from current `SELECTED_COLOR`).
- **REQ-10.5** The map background (`MapContainer` style) uses `background: '#0f172a'` to match the page background.

---

### REQ-11: Footer

- **REQ-11.1** A new `DashboardFooter` component is added below `DataTable` in `DashboardPage`.
- **REQ-11.2** The footer displays four labelled items in a responsive flex/grid row:
  - **Data Source** — value: "Zambia Data Hub / geoBoundaries"
  - **Reference Year** — value: the currently selected year
  - **Dataset** — value: the currently selected indicator name (or "—" if none)
  - **Notice** — value: "Demonstration data — not for official use"
- **REQ-11.3** The footer is visually separated from the content above by a `border-t border-white/8 mt-8 pt-6`.
- **REQ-11.4** Footer text is 11 px, `text-slate-500`. Labels are uppercase, tracking-widest.
- **REQ-11.5** The existing disclaimer paragraph in `DashboardPage` is removed and replaced by the footer.

---

### REQ-12: Accessibility and Responsiveness

- **REQ-12.1** All interactive elements retain visible `:focus-visible` outlines.
- **REQ-12.2** Colour contrast for body text on card backgrounds meets WCAG AA (4.5 : 1 minimum).
- **REQ-12.3** The layout reflows correctly at 375 px (mobile), 768 px (tablet), and 1280 px (desktop) viewport widths.
- **REQ-12.4** No `aria-*` attributes or roles are removed from existing components.
- **REQ-12.5** New icon elements carry `aria-hidden="true"` since they are decorative.

---

### REQ-13: No New Dependencies

- **REQ-13.1** No new npm packages are introduced. All icons are inline SVG. The Inter font is loaded via a CSS `@import` from Google Fonts CDN.
- **REQ-13.2** No Redux, Zustand, Jotai, or any state management library is introduced.
