# Implementation Plan: Interactive Zambia Province Map

## Overview

Add a province-level choropleth map to the StatFlow dashboard using React-Leaflet, a local Zambia province GeoJSON, and live analytics data from the existing API. No backend changes required.

## Tasks

- [x] 1. Obtain and commit Zambia province GeoJSON
  - Download Zambia administrative level-1 GeoJSON from geoBoundaries gbOpen (CC BY 4.0)
  - API: `https://www.geoboundaries.org/api/current/gbOpen/ZMB/ADM1/`
  - Verify the file contains exactly 10 features (one per province)
  - Verify each feature has a `shapeName` string property
  - Save as `frontend/public/zambia-provinces.geojson`
  - Add attribution in `ZambiaProvinceMap.jsx`: "Administrative boundaries: geoBoundaries, licensed under CC BY 4.0."
  - Do not fabricate or modify any boundary coordinates
  - Acceptance: file exists, `features.length === 10`, each feature has a `shapeName` property

- [x] 2. Implement choropleth utility functions
  - Create `frontend/src/utils/choropleth.js`
  - Implement `normaliseProvinceName(raw)` using the NAME_MAP in design.md
  - Implement `computeBins(values)` — returns 5 quintile break-points from a numeric array
  - Implement `getColor(value, bins)` — returns a PALETTE hex colour or NO_DATA_COLOR for null/undefined
  - Export constants: `PALETTE`, `NO_DATA_COLOR`, `SELECTED_COLOR`
  - Acceptance: all unit tests in Task 5 pass against these functions

- [x] 3. Implement `useZambiaGeoJSON` hook
  - Create `frontend/src/hooks/useZambiaGeoJSON.js`
  - Fetch `'/zambia-provinces.geojson'` once on mount (module-level cache prevents re-fetching)
  - Return `{ geojson, loading, error }`
  - Acceptance: hook returns geojson object after fetch, returns cached value on subsequent renders

- [x] 4. Implement `ZambiaProvinceMap` and `MapLegend` components
  - Create `frontend/src/components/dashboard/ZambiaProvinceMap.jsx`
  - Create `frontend/src/components/common/MapLegend.jsx`
  - Add `import 'leaflet/dist/leaflet.css'` to `frontend/src/main.jsx`
  - `ZambiaProvinceMap` accepts props: `chartData`, `provinces`, `selectedProvince`, `onProvinceSelect`, `unit`, `loading`, `error`
  - Uses `useZambiaGeoJSON` to load boundaries
  - Builds province-value lookup from `chartData` + `provinces` using `normaliseProvinceName`
  - Computes bins from `chartData` values and calls `getColor` per feature
  - Renders `<MapContainer>` with a `<GeoJSON>` layer; key changes on `chartData` to force re-style
  - Binds mouseover tooltip (province name, value, unit) and click handler
  - Click calls `onProvinceSelect(provinceId)` or `onProvinceSelect('')` if already selected
  - Selected province rendered with 2 px SELECTED_COLOR stroke
  - Shows loading overlay when `loading === true`
  - Shows error message when `error` is non-null
  - Shows neutral grey fill with informational message when `chartData` is empty
  - `MapLegend` renders five colour swatches with value ranges and a "No data" swatch
  - Acceptance: map renders in browser, provinces colour correctly, hover and click work

- [x] 5. Write choropleth utility unit tests
  - Create `frontend/src/test/choropleth.test.js`
  - Test `normaliseProvinceName` with all 12 inputs from NAME_MAP (including "North Western" → "North-Western")
  - Test `computeBins` returns exactly 5 break-points for a 10-value array
  - Test `getColor` at all five bin boundaries and midpoints
  - Test `getColor(null, bins)` returns `NO_DATA_COLOR`
  - Test `getColor(undefined, bins)` returns `NO_DATA_COLOR`
  - Acceptance: all tests pass with `npx vitest run`

- [x] 6. Write ZambiaProvinceMap integration tests
  - Add tests to `frontend/src/test/choropleth.test.js` or a new file
  - Mock `useZambiaGeoJSON` to return a minimal 2-feature GeoJSON with provinces "Lusaka" and "Copperbelt"
  - Mock `onProvinceSelect`
  - Test click-to-select: clicking "Lusaka" feature calls `onProvinceSelect` with the Lusaka UUID
  - Test deselect: clicking same province when already selected calls `onProvinceSelect('')`
  - Test no-data state: when `chartData` is empty, all features receive `NO_DATA_COLOR` fill
  - Test partial coverage: when only one of two provinces has data, the other receives `NO_DATA_COLOR`
  - Acceptance: all tests pass with `npx vitest run`

- [x] 7. Integrate map into DashboardPage
  - Update `frontend/src/pages/DashboardPage.jsx`
  - Import `ZambiaProvinceMap`
  - Pass `summary.results` (full, unfiltered) as `chartData` prop to the map
  - Pass `chartData` (filtered by selectedProvince) as before to `ProvinceSummary` and `DataTable`
  - Wire `selectedProvince`, `setSelectedProvince`, `provinces`, `unit`, `loading`, `error` props
  - Place map between `DashboardFilters` and `ProvinceSummary`
  - Acceptance: map appears in the dashboard, clicking a province updates the chart and table

- [x] 8. Verify all quality gates
  - Run `npx vitest run` — all tests pass (choropleth utils + integration + existing dashboard tests)
  - Run `npx oxlint` — exits 0 with no errors
  - Manually verify in browser: map loads, provinces colour correctly, hover tooltip works, click-to-select works, legend is visible
  - Verify mobile layout at ~375 px width: map fills width, legend is readable
  - Acceptance: all automated checks pass, no visual regressions

## Task Dependency Graph

```
1 (GeoJSON) ──► 2 (choropleth utils) ──► 5 (util tests)
                                     ──► 3 (useZambiaGeoJSON)
                                               │
                                               ▼
                                     4 (ZambiaProvinceMap + MapLegend)
                                               │
                                     ──► 6 (integration tests)
                                     ──► 7 (DashboardPage integration)
                                               │
                                               ▼
                                     8 (quality gates)
```

## Notes

- **GeoJSON source:** The Zambia province GeoJSON is sourced from geoBoundaries gbOpen (`geoBoundaries-ZMB-ADM1.geojson`), licensed under CC BY 4.0. Downloaded from `https://www.geoboundaries.org/api/current/gbOpen/ZMB/ADM1/` and saved at `frontend/public/zambia-provinces.geojson`. Province name property is `shapeName`.
- **Attribution:** `Administrative boundaries: geoBoundaries, licensed under CC BY 4.0.` — rendered in `ZambiaProvinceMap.jsx`.
- **No backend changes:** All data flows through the existing `/api/v1/analytics/indicator-summary` endpoint.
- **React-Leaflet and Leaflet** are already installed in `package.json`.
- The map passes `summary.results` (unfiltered) to `ZambiaProvinceMap` so all 10 provinces can be coloured; `chartData` (filtered) continues to drive `ProvinceSummary` and `DataTable`.
