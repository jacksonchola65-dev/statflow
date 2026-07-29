# Requirements: Interactive Zambia Province Map

## Overview

Add a province-level choropleth map to the StatFlow dashboard. The map displays live indicator values from the analytics API, colours each of Zambia's 10 provinces on a five-level accessible scale, and is wired into the existing shared dashboard filters so clicking a province immediately updates every other panel.

No backend APIs are modified. Geographic boundaries come from a local GeoJSON file — no fabricated data.

---

## Requirements

### REQ-1: Geographic Data

- **REQ-1.1** A local GeoJSON file containing exactly 10 polygons — one per Zambia province — must be committed to `frontend/public/zambia-provinces.geojson`.
- **REQ-1.2** The GeoJSON must be sourced from a reputable, openly-licensed dataset. Source used: geoBoundaries gbOpen (CC BY 4.0). Geographic boundaries must not be invented or approximated.
- **REQ-1.3** Each GeoJSON feature must carry a `shapeName` property (geoBoundaries convention) that can be matched to the StatFlow province names.
- **REQ-1.4** A deterministic name-mapping table must normalise GeoJSON feature names to StatFlow canonical names. The mapping covers all known variants.

**Canonical StatFlow province names (10):**

| StatFlow name | Expected GeoJSON variants |
|---|---|
| Central | Central |
| Copperbelt | Copperbelt |
| Eastern | Eastern |
| Luapula | Luapula |
| Lusaka | Lusaka |
| Muchinga | Muchinga |
| North-Western | North Western, NorthWestern, North-Western |
| Northern | Northern |
| Southern | Southern |
| Western | Western |

---

### REQ-2: Map Rendering

- **REQ-2.1** The map is rendered using React-Leaflet (`react-leaflet` ≥ v5, already installed).
- **REQ-2.2** Tile backgrounds are not required — the map uses vector fills only.
- **REQ-2.3** Province boundaries are drawn with a 1 px dark stroke.
- **REQ-2.4** The map fits all 10 Zambia provinces within its initial viewport with no manual pan required.
- **REQ-2.5** The map is responsive: it fills the available width on desktop and 100% on mobile. Minimum height is 320 px; default height is 480 px.

---

### REQ-3: Choropleth Colouring

- **REQ-3.1** Province fill colour is determined by the indicator value for that province in the current selection (indicator + year + optional dataset).
- **REQ-3.2** The colour scale has exactly five levels (quintiles or natural breaks, deterministic). Each level maps to a distinct accessible colour.
- **REQ-3.3** The colour scale uses an accessible sequential palette (e.g., ColorBrewer Blues or Oranges) — not red/green to avoid colour-blindness issues.
- **REQ-3.4** Provinces with no data for the current selection are rendered in a neutral grey (e.g., `#e0e0e0`) to distinguish them from the lowest-value bin.
- **REQ-3.5** The selected province (if any) is highlighted with a distinct stroke (2 px, accent colour).

---

### REQ-4: Legend

- **REQ-4.1** A visible legend is displayed inside or adjacent to the map.
- **REQ-4.2** The legend shows five colour swatches with their value ranges.
- **REQ-4.3** The legend includes a "No data" swatch.
- **REQ-4.4** The legend updates when the indicator or year changes.

---

### REQ-5: Hover Tooltip

- **REQ-5.1** Hovering over a province shows a tooltip containing:
  - Province name
  - Indicator value (formatted with commas)
  - Unit
- **REQ-5.2** Hovering over a province with no data shows the province name and "No data".
- **REQ-5.3** The tooltip does not obstruct the legend.

---

### REQ-6: Click-to-Select

- **REQ-6.1** Clicking a province calls `setSelectedProvince(provinceId)` from `useDashboardFilters`, where `provinceId` is the UUID from the StatFlow API.
- **REQ-6.2** Clicking an already-selected province clears the selection (`setSelectedProvince('')`).
- **REQ-6.3** The province click propagates immediately to the bar chart, data table, KPI grid, and filters dropdown.
- **REQ-6.4** The Filters panel Province dropdown and the map selection are kept in sync — changing one updates the other.

---

### REQ-7: Reactivity

- **REQ-7.1** The map re-colours when `selectedIndicatorId` changes.
- **REQ-7.2** The map re-colours when `selectedYear` changes.
- **REQ-7.3** The map re-colours when `datasetId` changes (if dataset filtering is in use).
- **REQ-7.4** The map does not re-fetch GeoJSON on indicator/year changes — GeoJSON is loaded once and cached.

---

### REQ-8: States

- **REQ-8.1** **Loading:** While analytics data is loading, provinces are rendered in the neutral grey "no-data" colour and a loading spinner overlays the map.
- **REQ-8.2** **Error:** If the analytics fetch fails, provinces are rendered in neutral grey and an error message is shown adjacent to the map.
- **REQ-8.3** **No data:** If all provinces lack data (empty results), all provinces render in neutral grey and an informational message is shown.
- **REQ-8.4** **Partial coverage:** Provinces present in the GeoJSON but absent from the analytics results render in neutral grey; provinces with data render normally.

---

### REQ-9: Tests

- **REQ-9.1** Province-name matching: the normalise function maps all expected GeoJSON name variants to the correct StatFlow canonical name (including "North-Western" variants).
- **REQ-9.2** Color-bin assignment: given a sorted array of values and five bins, the correct bin index is returned for boundary and mid-range values.
- **REQ-9.3** Click-to-select: clicking a province feature calls `setSelectedProvince` with the correct province UUID; clicking again calls it with `''`.
- **REQ-9.4** No-data handling: when `chartData` is empty the map renders all provinces in neutral grey.
- **REQ-9.5** Partial coverage: when only some provinces have data, those with data are coloured and those without are grey.

---

### REQ-10: Constraints

- **REQ-10.1** No backend API changes.
- **REQ-10.2** No district-level boundaries in this iteration.
- **REQ-10.3** No export functionality.
- **REQ-10.4** No authentication or user-session logic.
- **REQ-10.5** No trend charts or time-series animation.
- **REQ-10.6** No new npm packages beyond `react-leaflet` and `leaflet` (already installed).
