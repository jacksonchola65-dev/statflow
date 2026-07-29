# Requirements: Modular Dashboard Architecture Refactor

## Overview

Refactor the StatFlow React dashboard into a maintainable modular architecture using an app shell and reusable dashboard components, without changing any user-facing behavior.

The refactor is structurally complete — all components, hooks, routing, and page files already exist. The remaining work is to make the test suite pass and verify no regressions exist.

---

## Requirements

### REQ-1: Preserve All Existing Behavior

The refactor must not change any user-facing behavior.

- **REQ-1.1** Poverty Rate indicator (`POVERTY_RATE`) is automatically selected on load.
- **REQ-1.2** Year 2023 is selected by default.
- **REQ-1.3** Provinces, indicators, and analytics data load on mount.
- **REQ-1.4** Province filter narrows the chart and data table to the selected province.
- **REQ-1.5** Recharts bar chart renders province-level comparison data.
- **REQ-1.6** Retry button appears on reference data load failure and re-triggers the fetch.
- **REQ-1.7** Loading, error, and empty states render correctly in all scenarios.
- **REQ-1.8** "Demonstration data — not official statistics." disclaimer is visible on the page.
- **REQ-1.9** Mobile responsiveness is preserved (responsive grid, no fixed widths that break small screens).

### REQ-2: Component Architecture

All components listed below must exist, be correctly implemented, and be importable without errors.

- **REQ-2.1** Layout: `AppShell`, `Sidebar`, `Topbar`, `PageHeader`
- **REQ-2.2** Dashboard: `DashboardFilters`, `KpiCard`, `KpiGrid`, `ProvinceComparisonChart`, `ProvinceSummary`, `DataTable`
- **REQ-2.3** Common: `LoadingState`, `ErrorState`, `EmptyState`, `SelectField`
- **REQ-2.4** Hooks: `useDashboardFilters`, `useIndicatorSummary`
- **REQ-2.5** Page: `DashboardPage` (assembled from the components above)

### REQ-3: Routing

- **REQ-3.1** The dashboard is served at `/dashboard`.
- **REQ-3.2** Navigating to `/` redirects to `/dashboard`.
- **REQ-3.3** Any unmatched path renders `NotFoundPage`.

### REQ-4: Constraints

- **REQ-4.1** No Zambia map component (Leaflet is a dependency but not used in the dashboard yet).
- **REQ-4.2** No Redux or external state management library.
- **REQ-4.3** No backend API changes.
- **REQ-4.4** No new product features beyond what is specified here.
- **REQ-4.5** `HomePage.jsx` must not exist (removed if it was present).

### REQ-5: Frontend Tests

A Vitest + React Testing Library test suite must pass for `DashboardPage`:

- **REQ-5.1** Default Poverty Rate auto-selection verified.
- **REQ-5.2** Default year 2023 verified.
- **REQ-5.3** Loading state renders while reference data is pending.
- **REQ-5.4** Province bars appear in the chart after data loads.
- **REQ-5.5** Error state and retry button render on fetch failure.
- **REQ-5.6** Retry re-fetches data and clears the error on success.
- **REQ-5.7** Province filter hides non-matching rows.
- **REQ-5.8** Empty state renders when the API returns zero results.
- **REQ-5.9** Error state renders when chart data fetch fails.

### REQ-6: Quality Gates

- **REQ-6.1** `npx vitest run` exits with code 0 (all tests pass).
- **REQ-6.2** `npx oxlint` (lint) exits with code 0 (no lint errors).
- **REQ-6.3** No user-facing regression in the running app.
