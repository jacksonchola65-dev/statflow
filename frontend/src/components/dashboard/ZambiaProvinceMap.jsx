import { useCallback, useMemo } from 'react'
import { MapContainer, GeoJSON } from 'react-leaflet'
import { useZambiaGeoJSON } from '../../hooks/useZambiaGeoJSON'
import {
  normaliseProvinceName,
  computeBins,
  getColor,
  NO_DATA_COLOR,
  SELECTED_COLOR,
} from '../../utils/choropleth'
import MapLegend from '../common/MapLegend'

// ---------------------------------------------------------------------------
// Leaflet style constants
// Design-token hex values — Leaflet style objects cannot read CSS variables.
// ---------------------------------------------------------------------------

// Zambia centre coordinates and default zoom
const ZAMBIA_CENTER = [-13.1339, 27.8493]
const ZAMBIA_ZOOM   = 6

// Resting boundary stroke — slightly lighter than before for a refined look
const BASE_STYLE = {
  weight:      1,
  color:       '#475569', // slate-600 — subtle but visible boundary
  opacity:     1,
  fillOpacity: 0.80,
}

// Hover stroke — indigo-300, applied on mouseover, reset on mouseout
const HOVER_STROKE = { weight: 2, color: '#a5b4fc' } // indigo-300

/**
 * ZambiaProvinceMap — polished choropleth map of Zambia's 10 provinces.
 *
 * Visual changes from previous version
 * ─────────────────────────────────────
 * Card:
 *  - bg-slate-800/60 (was bg-gray-900)
 *  - border-[var(--sf-border)] (was border-white/10)
 *  - shadow + hover-shadow transition added
 * Map background:
 *  - #0f172a (= --sf-bg, slate-950) — was #111827
 * Boundary stroke:
 *  - resting: slate-600 #475569 — was #333333
 *  - hover:   indigo-300 #a5b4fc stroke, weight 2, via mouseover/mouseout
 *  - selected: orange-500 SELECTED_COLOR, weight 2 (unchanged from choropleth.js)
 * Tooltip:
 *  - styled with Leaflet `className` option for a dark glass look
 *  - no-data tooltip shows muted text
 * Overlays:
 *  - Loading/error/empty overlay backgrounds use slate-900/85 (was gray-900/80)
 *  - Loading spinner colour: indigo-400 (was blue-400)
 *  - Empty-data message uses token text colours
 * Attribution:
 *  - bg upgraded to white/80, backdrop-blur for polish — text & link preserved
 *
 * All prop signatures, click-to-select, deselect, and map behaviour unchanged.
 *
 * @param {{
 *   chartData:        Array<{ province_id: string, province_name: string, value: number }>,
 *   provinces:        Array<{ id: string, name: string }>,
 *   selectedProvince: string,
 *   onProvinceSelect: (id: string) => void,
 *   unit:             string,
 *   loading:          boolean,
 *   error:            string | null,
 * }} props
 */
export default function ZambiaProvinceMap({
  chartData = [],
  provinces = [],
  selectedProvince = '',
  onProvinceSelect,
  unit = '',
  loading = false,
  error = null,
}) {
  const { geojson, loading: geoLoading, error: geoError } = useZambiaGeoJSON()

  // ------------------------------------------------------------------
  // Build lookup: canonical province name → { value, provinceId }
  // ------------------------------------------------------------------
  const valueLookup = useMemo(() => {
    const map = new Map()

    for (const row of chartData) {
      const rawName =
        row.province_name ??
        provinces.find((p) => p.id === row.province_id)?.name ??
        ''
      const canonical = normaliseProvinceName(rawName)
      map.set(canonical, { value: row.value, provinceId: row.province_id })
    }
    return map
  }, [chartData, provinces])

  // ------------------------------------------------------------------
  // Compute colour bins from the current data values
  // ------------------------------------------------------------------
  const bins = useMemo(
    () => computeBins(chartData.map((r) => r.value)),
    [chartData],
  )

  // ------------------------------------------------------------------
  // styleFeature — returns Leaflet path options for each GeoJSON feature
  // ------------------------------------------------------------------
  const styleFeature = useCallback(
    (feature) => {
      const rawName  = feature?.properties?.shapeName ?? ''
      const canonical = normaliseProvinceName(rawName)
      const entry    = valueLookup.get(canonical)
      const fillColor = entry ? getColor(entry.value, bins) : NO_DATA_COLOR

      const isSelected = selectedProvince && entry?.provinceId === selectedProvince

      return {
        ...BASE_STYLE,
        fillColor,
        ...(isSelected
          ? { weight: 2, color: SELECTED_COLOR }
          : {}),
      }
    },
    [valueLookup, bins, selectedProvince],
  )

  // ------------------------------------------------------------------
  // bindEvents — attaches tooltip, hover highlight, and click handler
  // ------------------------------------------------------------------
  const bindEvents = useCallback(
    (feature, layer) => {
      const rawName   = feature?.properties?.shapeName ?? ''
      const canonical = normaliseProvinceName(rawName)
      const entry     = valueLookup.get(canonical)

      // Tooltip — styled via Leaflet tooltip class
      const valueStr = entry
        ? `${Number(entry.value).toLocaleString()}${unit ? ' ' + unit : ''}`
        : null

      const tooltipContent = valueStr
        ? `<strong style="font-size:13px;color:#f1f5f9">${canonical}</strong>` +
          `<br/><span style="color:#94a3b8;font-size:12px">${valueStr}</span>`
        : `<strong style="font-size:13px;color:#f1f5f9">${canonical}</strong>` +
          `<br/><em style="color:#64748b;font-size:12px">No data</em>`

      layer.bindTooltip(tooltipContent, {
        sticky:    true,
        direction: 'top',
        offset:    [0, -4],
        opacity:   1,
        className: 'sf-map-tooltip',
      })

      // Hover highlight — apply indigo stroke, reset on mouse-out
      layer.on('mouseover', () => {
        // Only apply hover stroke when not selected (selected has its own style)
        const isSelected = selectedProvince && entry?.provinceId === selectedProvince
        if (!isSelected) {
          layer.setStyle(HOVER_STROKE)
          layer.bringToFront()
        }
      })

      layer.on('mouseout', () => {
        // Reset to computed style (includes selected check)
        layer.setStyle(styleFeature(feature))
      })

      // Click — select / deselect province
      layer.on('click', () => {
        if (!onProvinceSelect) return
        const id = entry?.provinceId ?? ''
        if (id && id === selectedProvince) {
          onProvinceSelect('')
        } else {
          onProvinceSelect(id)
        }
      })
    },
    [valueLookup, unit, onProvinceSelect, selectedProvince, styleFeature],
  )

  // ------------------------------------------------------------------
  // Stable key — forces GeoJSON layer remount when chartData changes
  // ------------------------------------------------------------------
  const geoJsonKey = useMemo(
    () => chartData.map((r) => `${r.province_id}:${r.value}`).join('|'),
    [chartData],
  )

  // ------------------------------------------------------------------
  // Derived UI states
  // ------------------------------------------------------------------
  const isLoading    = loading || geoLoading
  const displayError = error || geoError
  const isEmpty      = !isLoading && !displayError && chartData.length === 0

  const ariaLabel = unit
    ? `Zambia province map — values in ${unit}`
    : 'Zambia province map'

  return (
    <section
      className="
        rounded-xl
        border border-[var(--sf-border)]
        bg-slate-800/60
        p-4 sm:p-6
        shadow-[var(--sf-shadow-card)]
        hover:shadow-[var(--sf-shadow-card-hover)]
        transition-shadow duration-200
      "
    >
      {/* Card header */}
      <div className="mb-4">
        <p
          className="
            text-[11px] font-medium uppercase
            tracking-[var(--sf-tracking-widest)]
            text-[var(--sf-text-subtle)]
            mb-1
          "
        >
          Province choropleth
        </p>
        <h2 className="text-xl font-semibold text-white leading-tight">
          Zambia — Province Map
          {unit && (
            <span className="ml-2 text-sm font-normal text-[var(--sf-text-muted)]">
              ({unit})
            </span>
          )}
        </h2>
      </div>

      {/* Map wrapper — relative for overlay positioning */}
      <div
        className="relative w-full rounded-lg overflow-hidden"
        style={{ height: 480, minHeight: 320 }}
        role="img"
        aria-label={ariaLabel}
      >
        {/* ---- Leaflet map ---- */}
        {geojson && (
          <MapContainer
            center={ZAMBIA_CENTER}
            zoom={ZAMBIA_ZOOM}
            style={{ height: '100%', width: '100%', background: '#0f172a' }}
            zoomControl
            attributionControl={false}
          >
            <GeoJSON
              key={geoJsonKey || 'empty'}
              data={geojson}
              style={styleFeature}
              onEachFeature={bindEvents}
            />
          </MapContainer>
        )}

        {/* ---- Loading overlay ---- */}
        {isLoading && (
          <div
            className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/85 z-[1000]"
            aria-live="polite"
            aria-busy="true"
          >
            <svg
              className="animate-spin h-8 w-8 text-indigo-400 mb-3"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12" cy="12" r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v8H4z"
              />
            </svg>
            <p className="text-sm text-[var(--sf-text-muted)]">Loading map data…</p>
          </div>
        )}

        {/* ---- Error overlay ---- */}
        {!isLoading && displayError && (
          <div
            className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/85 z-[1000] px-4"
            role="alert"
          >
            <p className="text-rose-400 text-sm text-center">{displayError}</p>
          </div>
        )}

        {/* ---- No-data informational message ---- */}
        {isEmpty && (
          <div
            className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-[1000] px-4"
            aria-live="polite"
          >
            <p
              className="
                text-[var(--sf-text-muted)] text-sm text-center
                bg-slate-900/75 backdrop-blur-sm
                border border-white/8
                px-4 py-2.5 rounded-lg
              "
            >
              No indicator data for the current selection — provinces shown in neutral grey.
            </p>
          </div>
        )}

        {/* ---- Legend (bottom-right, inside map) ---- */}
        <div className="absolute bottom-8 right-3 z-[1000]">
          <MapLegend bins={bins} unit={unit} />
        </div>

        {/* ---- Attribution (bottom-left, preserved from geoBoundaries requirement) ---- */}
        <div
          className="
            absolute bottom-0 left-0 z-[1000]
            px-2 py-0.5
            bg-white/80 backdrop-blur-sm
            text-slate-600 text-[10px]
            rounded-tr
            pointer-events-none
          "
        >
          Administrative boundaries:{' '}
          <a
            href="https://www.geoboundaries.org"
            target="_blank"
            rel="noopener noreferrer"
            className="underline pointer-events-auto hover:text-slate-800 transition-colors"
          >
            geoBoundaries
          </a>
          , licensed under CC BY 4.0.
        </div>
      </div>
    </section>
  )
}
