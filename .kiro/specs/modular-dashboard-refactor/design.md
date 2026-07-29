# Design: Modular Dashboard Architecture Refactor

## Overview

The modular architecture is already implemented. This design document describes the final target state — the file tree, component contracts, data flow, and test infrastructure — so that any remaining gaps (notably the failing test suite) can be closed precisely.

---

## File Tree (Target State)

```
frontend/src/
├── app/
│   └── router.jsx                  # BrowserRouter routes: / → /dashboard, /dashboard, *
├── components/
│   ├── common/
│   │   ├── EmptyState.jsx
│   │   ├── ErrorState.jsx
│   │   ├── LoadingState.jsx
│   │   └── SelectField.jsx
│   ├── dashboard/
│   │   ├── DashboardFilters.jsx
│   │   ├── DataTable.jsx
│   │   ├── KpiCard.jsx
│   │   ├── KpiGrid.jsx
│   │   ├── ProvinceComparisonChart.jsx
│   │   └── ProvinceSummary.jsx
│   └── layout/
│       ├── AppShell.jsx
│       ├── PageHeader.jsx
│       ├── Sidebar.jsx
│       └── Topbar.jsx
├── hooks/
│   ├── useDashboardFilters.js
│   └── useIndicatorSummary.js
├── pages/
│   ├── DashboardPage.jsx
│   └── NotFoundPage.jsx
├── services/
│   └── api.js
├── test/
│   ├── DashboardPage.test.jsx
│   └── setup.js
├── App.jsx
├── index.css
└── main.jsx
```

No `HomePage.jsx` should exist.

---

## Component Contracts

### Layout

#### `AppShell`
- Props: `{ children: ReactNode }`
- Renders: full-screen dark layout with `<Topbar />` across the top, `<Sidebar />` on the left, and a `<main>` content area.
- The `<main>` is padded and max-width constrained for readability.

#### `Topbar`
- Props: none
- Renders: `StatFlow` branding with `Development Indicators` tagline.

#### `Sidebar`
- Props: none
- Renders: `null` (placeholder for future navigation; currently empty).

#### `PageHeader`
- Props: `{ title: string, subtitle?: string }`
- Renders: `<h2>` with optional subtitle paragraph. Used to label page sections.

---

### Common

#### `SelectField`
- Props: `{ label, value, onChange, disabled?, children }`
- Renders a labeled `<select>` with consistent dark-theme styling.
- `onChange` receives the string value from `e.target.value`.
- Must render an accessible `<label>` associated with the `<select>` via text content (for `getByRole('combobox', { name: /label/i })`).

#### `LoadingState`
- Props: `{ message?: string }` (default: `"Loading…"`)
- Renders a centered spinner + message.

#### `ErrorState`
- Props: `{ message: string, onRetry?: () => void, retrying?: boolean }`
- Renders `role="alert"` container.
- Shows "Retry" button only when `onRetry` is provided.
- Button is disabled and shows "Retrying…" when `retrying` is true.

#### `EmptyState`
- Props: `{ message?: string }` (default: `"No data available for this selection."`)
- Renders a centered empty-state illustration + message.

---

### Dashboard

#### `DashboardFilters`
- Props: provinces, indicators, selectedProvince, selectedIndicatorId, selectedYear, disabled, onChange handlers.
- Renders three `<SelectField>` controls: Province, Indicator, Year.

#### `KpiCard`
- Props: `{ label: string, value: string | number, unit?: string }`
- Renders a single metric tile.

#### `KpiGrid`
- Props: `{ items: Array<{label, value, unit?}> }`
- Renders a responsive grid of `KpiCard`s. Returns `null` when `items` is empty.

#### `ProvinceComparisonChart`
- Props: `{ data, unit, selectedProvince }`
- Renders a Recharts `BarChart` with province codes on X-axis and indicator values on Y-axis.
- Each bar highlighted at 85% opacity when no province filter is active.

#### `ProvinceSummary`
- Props: `{ loading, error, chartData, unit, selectedProvince, selectedIndicatorName, selectedYear }`
- Delegates to `LoadingState`, `ErrorState`, `EmptyState`, or `ProvinceComparisonChart` based on state.
- Chart error rendered without a retry button (chart errors are informational; reference data errors have retry).

#### `DataTable`
- Props: `{ rows, unit? }`
- Renders province name + value table. Returns `null` when `rows` is empty.

---

### Hooks

#### `useDashboardFilters`
- Fetches provinces and indicators in parallel via `Promise.all`.
- Auto-selects the indicator with `code === 'POVERTY_RATE'` after load.
- Default year: `2023`.
- Exposes `loadRefData` for manual retry.
- Uses a `loadingRef` guard to prevent duplicate concurrent requests.

#### `useIndicatorSummary`
- Fetches `fetchIndicatorSummary` whenever `indicatorId` or `year` changes.
- Derives `chartData` via `useMemo` — filters by `provinceFilter` if set.
- Returns `{ summary, loading, error, chartData }`.

---

## Data Flow

```
App
└── BrowserRouter
    └── AppRouter
        └── /dashboard → DashboardPage
            ├── useDashboardFilters()  ← fetchProvinces + fetchIndicators
            ├── useIndicatorSummary()  ← fetchIndicatorSummary
            ├── AppShell
            │   ├── Topbar
            │   ├── Sidebar (null)
            │   └── main
            │       ├── ErrorState (ref data error + retry)
            │       ├── DashboardFilters
            │       ├── ProvinceSummary
            │       │   ├── LoadingState | ErrorState | EmptyState
            │       │   └── ProvinceComparisonChart
            │       ├── DataTable
            │       └── disclaimer <p>
```

---

## Test Infrastructure

### Framework
- **Vitest** (runner) + **jsdom** (environment) + **React Testing Library** + **@testing-library/jest-dom**
- Configuration in `vite.config.js` under the `test` key.

### Known Issue: `React is not defined` in Tests

**Root cause:** The JSX files use the automatic JSX transform (no `import React from 'react'`). The Vite plugin is configured with `jsxRuntime: 'automatic'`, but Vitest's transform pipeline needs the React automatic runtime to be set explicitly via the `@vitejs/plugin-react` Babel configuration or via a `jsxImportSource` setting.

**Fix:** Ensure `vite.config.js` (used by Vitest) correctly configures the React plugin so the automatic JSX runtime is injected during test transforms. The standard fix is to confirm that `@vitejs/plugin-react` is used with no additional flags needed — but the `jsxRuntime: 'automatic'` option passed to the plugin must be respected by the Vitest transform. If still failing, add `import React from 'react'` to the `setup.js` as a global, or configure `globals: { React: ... }` — the cleanest fix is verifying the plugin config and/or adding a `react()` plugin call without overrides.

### Test Coverage (DashboardPage.test.jsx)

| Test | Description |
|------|-------------|
| auto-selects Poverty Rate on load | `<select name="indicator">` value === `ind-1` after load |
| auto-selects 2023 as default year | `<select name="year">` value === `"2023"` after load |
| shows loading state | `"Loading…"` text visible while promises are pending |
| renders province chart bars | Province names appear in data table after load |
| shows error state on failure | `role="alert"` and error text visible |
| shows Retry button | Retry button present in error state |
| retries on Retry click | Second fetch succeeds; alert disappears |
| filters chart to one province | Selecting Central hides Lusaka from data table |
| shows empty state | `"No data available"` when results array is empty |
| displays disclaimer | `"Demonstration data"` text present |

---

## Constraints Summary

| Constraint | Detail |
|------------|--------|
| No map | Leaflet installed but not used in dashboard |
| No Redux | React state + custom hooks only |
| No backend changes | Frontend-only refactor |
| No new features | Behavior-preserving refactor only |
| No `HomePage.jsx` | File must not exist |
| Mobile responsive | Tailwind responsive grid classes preserved |
