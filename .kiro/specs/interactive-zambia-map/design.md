# Design: Interactive Zambia Province Map

## Overview

A choropleth map component integrated into the existing modular dashboard. GeoJSON is loaded once from `public/zambia-provinces.geojson`, analytics data is supplied by `useIndicatorSummary`, and province selection is wired through `useDashboardFilters`. All logic is pure JavaScript — no new state management layers.

---

## File Changes

```
frontend/
├── public/
│   └── zambia-provinces.geojson        NEW — local GeoJSON (sourced externally)
└── src/
    ├── components/
    │   ├── dashboard/
    │   │   └── ZambiaProvinceMap.jsx    NEW — choropleth map component
    │   └── common/
    │       └── MapLegend.jsx            NEW — five-level colour legend
    ├── hooks/
    │   └── useZambiaGeoJSON.js          NEW — fetches & caches GeoJSON once
    ├── utils/
    │   └── choropleth.js               NEW — colour scale + name normalisation
    └── test/
        └── choropleth.test.js          NEW — pure-function unit tests
```

`DashboardPage.jsx` is updated to include `ZambiaProvinceMap` between `DashboardFilters` and `ProvinceSummary`.

No backend files are changed.

---

## GeoJSON Source

**Required:** A Zambia administrative level-1 (province) GeoJSON with 10 features.

Source used:
- **geoBoundaries gbOpen** — `geoBoundaries-ZMB-ADM1.geojson` (CC BY 4.0)  
  API: `https://www.geoboundaries.org/api/current/gbOpen/ZMB/ADM1/`  
  Direct download: `https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/ZMB/ADM1/geoBoundaries-ZMB-ADM1.geojson`  
  License: Creative Commons Attribution 4.0 International (CC BY 4.0)  
  Source: Zambia Data Hub via William & Mary geoLab  

The file was downloaded and saved at `frontend/public/zambia-provinces.geojson`. It is not fetched at runtime from an external URL.

**Attribution required in the UI:**  
`Administrative boundaries: geoBoundaries, licensed under CC BY 4.0.`

**Property used for name matching:** `shapeName` (geoBoundaries convention).

---

## Province Name Mapping

Defined in `src/utils/choropleth.js`:

```js
const NAME_MAP = {
  'Central':       'Central',
  'Copperbelt':    'Copperbelt',
  'Eastern':       'Eastern',
  'Luapula':       'Luapula',
  'Lusaka':        'Lusaka',
  'Muchinga':      'Muchinga',
  'North Western': 'North-Western',
  'NorthWestern':  'North-Western',
  'North-Western': 'North-Western',  // geoBoundaries uses this exact form
  'Northern':      'Northern',
  'Southern':      'Southern',
  'Western':       'Western',
}

export function normaliseProvinceName(raw) {
  return NAME_MAP[raw?.trim()] ?? raw?.trim() ?? ''
}
```

---

## Colour Scale

Five-level sequential scale defined in `src/utils/choropleth.js`:

```js
// ColorBrewer Blues (5-class) — accessible, perceptually uniform
const PALETTE = ['#eff3ff', '#bdd7e7', '#6baed6', '#3182bd', '#08519c']
const NO_DATA_COLOR = '#e0e0e0'
const SELECTED_COLOR = '#f97316'  // orange-500 accent stroke

export function computeBins(values) { /* quintile breaks */ }
export function getColor(value, bins) { /* returns PALETTE[binIndex] */ }
```

Bins are computed from the **current dataset's values** (not global min/max) so the scale fills the full range.

---

## Component Architecture

### `useZambiaGeoJSON`

```js
export function useZambiaGeoJSON() {
  // Fetches '/zambia-provinces.geojson' once on mount
  // Returns { geojson, loading, error }
  // Caches in module-level variable — re-renders don't re-fetch
}
```

### `ZambiaProvinceMap`

Props:
```ts
{
  chartData:           Array<ProvinceResult>  // from useIndicatorSummary
  provinces:           Array<Province>        // from useDashboardFilters
  selectedProvince:    string                 // province UUID or ''
  onProvinceSelect:    (id: string) => void
  unit:                string
  loading:             boolean
  error:               string | null
}
```

Internal logic:
1. Load GeoJSON via `useZambiaGeoJSON`.
2. Build a lookup: `Map<canonicalName, { value, provinceId }>` from `chartData` + `provinces`.
3. Compute bins from the values in `chartData`.
4. Render `<MapContainer>` with `<GeoJSON key={stableKey} data={geojson} style={styleFeature} onEachFeature={bindEvents} />`.
5. `styleFeature(feature)` → looks up canonical name, returns fill colour or `NO_DATA_COLOR`.
6. `bindEvents(feature, layer)` → attaches `mouseover` (show tooltip), `mouseout` (hide tooltip), `click` (call `onProvinceSelect`).
7. Overlay: spinner when `loading`, error banner when `error`.

**Key re-render strategy:** The `<GeoJSON>` component receives a `key` prop that changes when `chartData` changes — this forces React-Leaflet to re-mount the layer with fresh styles, avoiding stale fill colours from the previous render.

### `MapLegend`

Rendered as a Leaflet `<Control position="bottomright">` or a plain positioned `<div>` outside the map.

Props:
```ts
{ bins: number[], unit: string }
```

Renders five swatches + range labels + "No data" swatch.

---

## DashboardPage Integration

```jsx
// After DashboardFilters, before ProvinceSummary:
<ZambiaProvinceMap
  chartData={chartData}
  provinces={provinces}
  selectedProvince={selectedProvince}
  onProvinceSelect={setSelectedProvince}
  unit={unit}
  loading={refLoading || chartLoading}
  error={chartError}
/>
```

`chartData` is already filtered by `selectedProvince` in `useIndicatorSummary`. When the map is shown, the `provinceFilter` in `useIndicatorSummary` will show all province data (no filter applied) so the map can colour all provinces. Only the DataTable and chart below the map apply the filter.

> Note: This may require a design adjustment — `useIndicatorSummary` should receive `provinceFilter` only for the chart/table, not for the map. `ZambiaProvinceMap` always receives the full unfiltered `chartData`. This is handled by passing `summary.results` (unfiltered) to the map and `chartData` (filtered) to `ProvinceSummary` and `DataTable`.

---

## Data Flow

```
useDashboardFilters
  └── provinces[]        ─────────────────────────────┐
  └── selectedProvince   ──── ZambiaProvinceMap         │
  └── setSelectedProvince ─── (click handler)           │
                                                        │
useIndicatorSummary                                     │
  └── summary.results    ──── ZambiaProvinceMap (full) ─┘
  └── chartData          ──── ProvinceSummary + DataTable (filtered)
  └── unit               ──── ZambiaProvinceMap + ProvinceSummary
```

---

## Test Strategy

All tests live in `src/test/choropleth.test.js` and test pure utility functions only — no DOM rendering required for the core logic.

| Test | Approach |
|------|----------|
| Province name normalisation | Unit test `normaliseProvinceName` with all 12 expected inputs |
| Bin computation | Unit test `computeBins` with a known array of 10 values |
| Color assignment | Unit test `getColor` at bin boundaries and midpoints |
| No-data color | Assert `getColor(null, bins) === NO_DATA_COLOR` |
| Click-to-select | RTL test: render `ZambiaProvinceMap` with mock GeoJSON, simulate click, assert `onProvinceSelect` called with correct UUID |
| Deselect on second click | Same as above but `selectedProvince` is already set |
| Partial coverage | Assert features not in `chartData` receive `NO_DATA_COLOR` fill |

---

## Leaflet CSS

Leaflet requires its CSS to be imported. Add to `main.jsx`:
```js
import 'leaflet/dist/leaflet.css'
```

Or import it in `ZambiaProvinceMap.jsx` directly. This import must come before any Leaflet usage.

---

## Leaflet Default Icon Fix

React-Leaflet has a known default marker icon issue with Vite. Since this feature uses only `GeoJSON` layers (no markers), no icon fix is needed.

---

## Accessibility

- Map container has `role="img"` and `aria-label="Zambia province map showing [indicator name]"`.
- Legend is a visible HTML element (not inside the canvas/SVG layer), accessible to screen readers.
- Colour palette is tested for contrast against the dark page background.
