import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect } from 'vitest'
import ZambiaProvinceMap from '../components/dashboard/ZambiaProvinceMap'
import { NO_DATA_COLOR } from '../utils/choropleth'

// ---------------------------------------------------------------------------
// Mock leaflet CSS (avoid import errors in test env)
// ---------------------------------------------------------------------------
vi.mock('leaflet/dist/leaflet.css', () => ({}))

// ---------------------------------------------------------------------------
// Mock react-leaflet — render features as divs so we can query and click them
// ---------------------------------------------------------------------------
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div data-testid="map-container">{children}</div>,
  GeoJSON: ({ data, style, onEachFeature }) => {
    if (!data?.features) return null
    return (
      <div data-testid="geojson-layer">
        {data.features.map((feature, i) => {
          const name = feature.properties.shapeName
          const featureStyle = style ? style(feature) : {}
          // Create a mock layer with event-handler capture
          const mockLayer = {
            bindTooltip: vi.fn(),
            on: vi.fn((event, handler) => {
              if (event === 'click') mockLayer._clickHandler = handler
            }),
            _clickHandler: null,
          }
          if (onEachFeature) onEachFeature(feature, mockLayer)
          return (
            <div
              key={i}
              data-testid={`feature-${name.toLowerCase()}`}
              data-fill={featureStyle.fillColor}
              onClick={() => mockLayer._clickHandler && mockLayer._clickHandler()}
            >
              {name}
            </div>
          )
        })}
      </div>
    )
  },
}))

// ---------------------------------------------------------------------------
// Minimal GeoJSON fixture — two Zambia provinces
// ---------------------------------------------------------------------------
const MOCK_GEOJSON = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { shapeName: 'Lusaka' },
      geometry: {
        type: 'Polygon',
        coordinates: [[[27.0, -15.0], [28.0, -15.0], [28.0, -16.0], [27.0, -16.0], [27.0, -15.0]]],
      },
    },
    {
      type: 'Feature',
      properties: { shapeName: 'Copperbelt' },
      geometry: {
        type: 'Polygon',
        coordinates: [[[26.0, -12.0], [29.0, -12.0], [29.0, -14.0], [26.0, -14.0], [26.0, -12.0]]],
      },
    },
  ],
}

// ---------------------------------------------------------------------------
// Mock useZambiaGeoJSON — immediately return fixture data, no network
// ---------------------------------------------------------------------------
vi.mock('../hooks/useZambiaGeoJSON', () => ({
  useZambiaGeoJSON: () => ({ geojson: MOCK_GEOJSON, loading: false, error: null }),
}))

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------
const PROVINCES = [
  { id: 'lusaka-uuid', name: 'Lusaka' },
  { id: 'copperbelt-uuid', name: 'Copperbelt' },
]

const CHART_DATA_BOTH = [
  { province_id: 'lusaka-uuid', province_name: 'Lusaka', value: 30 },
  { province_id: 'copperbelt-uuid', province_name: 'Copperbelt', value: 70 },
]

const CHART_DATA_LUSAKA_ONLY = [
  { province_id: 'lusaka-uuid', province_name: 'Lusaka', value: 50 },
]

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------
function renderMap(props = {}) {
  const defaults = {
    chartData: CHART_DATA_BOTH,
    provinces: PROVINCES,
    selectedProvince: '',
    onProvinceSelect: vi.fn(),
    unit: '%',
  }
  return render(<ZambiaProvinceMap {...defaults} {...props} />)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ZambiaProvinceMap integration', () => {
  describe('click-to-select', () => {
    it('calls onProvinceSelect with the province UUID when a feature is clicked', async () => {
      const user = userEvent.setup()
      const onProvinceSelect = vi.fn()

      renderMap({ onProvinceSelect, selectedProvince: '' })

      const lusakaFeature = screen.getByTestId('feature-lusaka')
      await user.click(lusakaFeature)

      expect(onProvinceSelect).toHaveBeenCalledTimes(1)
      expect(onProvinceSelect).toHaveBeenCalledWith('lusaka-uuid')
    })
  })

  describe('deselect', () => {
    it('calls onProvinceSelect with empty string when already-selected province is clicked again', async () => {
      const user = userEvent.setup()
      const onProvinceSelect = vi.fn()

      // Province is already selected
      renderMap({ onProvinceSelect, selectedProvince: 'lusaka-uuid' })

      const lusakaFeature = screen.getByTestId('feature-lusaka')
      await user.click(lusakaFeature)

      expect(onProvinceSelect).toHaveBeenCalledTimes(1)
      expect(onProvinceSelect).toHaveBeenCalledWith('')
    })
  })

  describe('no-data state', () => {
    it('assigns NO_DATA_COLOR fill to all features when chartData is empty', () => {
      renderMap({ chartData: [], selectedProvince: '' })

      const lusakaFeature = screen.getByTestId('feature-lusaka')
      const copperbeltFeature = screen.getByTestId('feature-copperbelt')

      expect(lusakaFeature.dataset.fill).toBe(NO_DATA_COLOR)
      expect(copperbeltFeature.dataset.fill).toBe(NO_DATA_COLOR)
    })
  })

  describe('partial coverage', () => {
    it('assigns NO_DATA_COLOR only to the province without data when one province is missing', () => {
      renderMap({ chartData: CHART_DATA_LUSAKA_ONLY, selectedProvince: '' })

      const lusakaFeature = screen.getByTestId('feature-lusaka')
      const copperbeltFeature = screen.getByTestId('feature-copperbelt')

      // Lusaka has data — should NOT be NO_DATA_COLOR
      expect(lusakaFeature.dataset.fill).not.toBe(NO_DATA_COLOR)
      // Copperbelt has no data — must be NO_DATA_COLOR
      expect(copperbeltFeature.dataset.fill).toBe(NO_DATA_COLOR)
    })
  })
})
