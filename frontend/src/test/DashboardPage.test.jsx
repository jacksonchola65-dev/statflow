import React from 'react'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import DashboardPage from '../pages/DashboardPage'
import * as api from '../services/api'

const authState = vi.hoisted(() => ({
  user: { id: '1', email: 'admin@example.com', role: 'ADMIN', full_name: 'Admin User' },
  isAuthenticated: true,
}))

// ---------------------------------------------------------------------------
// Mock AuthContext so Topbar (inside AppShell) doesn't need a real provider
// ---------------------------------------------------------------------------

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user:            authState.user,
    isAuthenticated: authState.isAuthenticated,
    isLoading:       false,
    csrfToken:       'mock-csrf',
    login:           vi.fn(),
    logout:          vi.fn(),
    refreshSession:  vi.fn(),
  }),
  AuthProvider: ({ children }) => children,
}))

// ---------------------------------------------------------------------------
// Mock API module
// ---------------------------------------------------------------------------

vi.mock('../services/api', () => ({
  fetchProvinces: vi.fn(),
  fetchIndicators: vi.fn(),
  fetchIndicatorSummary: vi.fn(),
}))

// Mock useZambiaGeoJSON so it never fires a real fetch in jsdom.
// Without this mock the hook's fetch() rejects immediately (no server in
// test environment) and the resulting setError/setLoading calls fire outside
// act(), producing React act() warnings on every test that renders DashboardPage.
vi.mock('../hooks/useZambiaGeoJSON', () => ({
  useZambiaGeoJSON: () => ({ geojson: null, loading: false, error: null }),
}))

const PROVINCES = [
  { id: 'prov-1', code: 'CP', name: 'Central' },
  { id: 'prov-2', code: 'LK', name: 'Lusaka' },
]

const INDICATORS = [
  { id: 'ind-1', code: 'POVERTY_RATE', name: 'Poverty Rate', unit: 'Percent' },
  { id: 'ind-2', code: 'LITERACY_RATE', name: 'Literacy Rate', unit: '%' },
]

const SUMMARY = {
  indicator_id: 'ind-1',
  dataset_id: 'ds-1',
  reference_year: 2023,
  unit: 'Percent',
  results: [
    { province_id: 'prov-1', province_code: 'CP', province_name: 'Central',  value: '55.2000' },
    { province_id: 'prov-2', province_code: 'LK', province_name: 'Lusaka',   value: '24.3000' },
  ],
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <DashboardPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  authState.user = { id: '1', email: 'admin@example.com', role: 'ADMIN', full_name: 'Admin User' }
  authState.isAuthenticated = true
  api.fetchProvinces.mockResolvedValue(PROVINCES)
  api.fetchIndicators.mockResolvedValue(INDICATORS)
  api.fetchIndicatorSummary.mockResolvedValue(SUMMARY)
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DashboardPage', () => {
  it('welcomes the user by first name and positions StatFlow broadly', () => {
    renderDashboard()

    expect(screen.getByRole('heading', { name: /good morning, admin/i })).toBeInTheDocument()
    expect(screen.getByText(/trusted public evidence and your organization's permitted data/i)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /ask statflow/i })).toBeInTheDocument()
  })

  it('uses a generic greeting when the user has no full name', () => {
    authState.user = { id: '1', email: 'admin@example.com', role: 'ADMIN', full_name: '' }
    renderDashboard()

    expect(screen.getByRole('heading', { name: /good morning, there/i })).toBeInTheDocument()
  })

  it('distinguishes the available example from future product direction', () => {
    renderDashboard()

    expect(screen.getByText('Available now')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /which district in luapula/i })).toBeInTheDocument()
    expect(screen.getByText(/upcoming capabilities, not active production analyses/i)).toBeInTheDocument()
  })

  it('keeps Bring your data actionable only for permitted roles', () => {
    authState.user = { id: '1', email: 'viewer@example.com', role: 'VIEWER', full_name: 'Viewer User' }
    renderDashboard()

    expect(screen.getByLabelText('Bring your data unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /open data import/i })).not.toBeInTheDocument()
  })

  it('hands an entered question to the existing Decision Workspace route', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/decisions" element={<div>Decision Workspace destination</div>} />
        </Routes>
      </MemoryRouter>,
    )

    const input = screen.getByRole('textbox', { name: /ask statflow/i })
    await user.type(input, 'Which district in Luapula is best for a supermarket?')
    await user.click(screen.getByRole('button', { name: 'Ask StatFlow' }))

    expect(await screen.findByText('Decision Workspace destination')).toBeInTheDocument()
  })

  it('auto-selects Poverty Rate on load', async () => {
    renderDashboard()
    await waitFor(() => {
      const select = screen.getByRole('combobox', { name: /indicator/i })
      expect(select.value).toBe('ind-1')
    })
  })

  it('auto-selects 2023 as the default year', async () => {
    renderDashboard()
    await waitFor(() => {
      const select = screen.getByRole('combobox', { name: /year/i })
      expect(select.value).toBe('2023')
    })
  })

  it('shows loading state while reference data loads', () => {
    // Keep the promise pending
    api.fetchProvinces.mockReturnValue(new Promise(() => {}))
    api.fetchIndicators.mockReturnValue(new Promise(() => {}))
    renderDashboard()
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('renders province chart bars after data loads', async () => {
    renderDashboard()
    // Provinces appear in the DataTable (which renders in jsdom; chart SVG does not)
    await waitFor(() => {
      expect(screen.getByText('Central')).toBeInTheDocument()
      expect(screen.getByText('Lusaka')).toBeInTheDocument()
    }, { timeout: 5000 })
  })

  it('shows error state when reference data fails', async () => {
    api.fetchProvinces.mockRejectedValue(new Error('Network error'))
    api.fetchIndicators.mockRejectedValue(new Error('Network error'))
    renderDashboard()
    await waitFor(() => {
      // There may be multiple alerts (e.g. map GeoJSON error overlay), so
      // use getAllByRole and confirm the ref-data alert is present by text.
      const alerts = screen.getAllByRole('alert')
      expect(alerts.length).toBeGreaterThanOrEqual(1)
      expect(screen.getByText(/network error/i)).toBeInTheDocument()
    })
  })

  it('shows Retry button in error state', async () => {
    api.fetchProvinces.mockRejectedValue(new Error('Network error'))
    api.fetchIndicators.mockRejectedValue(new Error('Network error'))
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
    })
  })

  it('retries loading when Retry is clicked', async () => {
    const user = userEvent.setup()
    api.fetchProvinces.mockRejectedValueOnce(new Error('fail'))
    api.fetchIndicators.mockRejectedValueOnce(new Error('fail'))
    // Second call succeeds
    api.fetchProvinces.mockResolvedValue(PROVINCES)
    api.fetchIndicators.mockResolvedValue(INDICATORS)

    renderDashboard()
    await waitFor(() => screen.getByRole('button', { name: /retry/i }))

    await user.click(screen.getByRole('button', { name: /retry/i }))

    await waitFor(() => {
      // The ref-data error banner is cleared after a successful retry.
      // The map's GeoJSON overlay may still show (jsdom cannot fetch local files),
      // so assert the specific network-error text is gone, not all alerts.
      expect(screen.queryByText(/network error/i)).not.toBeInTheDocument()
    })
  })

  it('filters chart to one province when a province is selected', async () => {
    const user = userEvent.setup()
    renderDashboard()

    // Wait for data to load — table appears once data is ready
    const table = await screen.findByRole('table', {}, { timeout: 5000 })
    expect(within(table).getByText('Central')).toBeInTheDocument()
    expect(within(table).getByText('Lusaka')).toBeInTheDocument()

    // SelectField now has htmlFor/id so getByRole works with accessible name
    const provinceSelect = screen.getByRole('combobox', { name: /province/i })
    await user.selectOptions(provinceSelect, 'prov-1')  // Central

    await waitFor(() => {
      // Lusaka row should disappear from the data table
      expect(within(table).queryByText('Lusaka')).not.toBeInTheDocument()
      // Central row should remain
      expect(within(table).getByText('Central')).toBeInTheDocument()
    })
  })

  it('shows empty state when no chart data is available', async () => {
    api.fetchIndicatorSummary.mockResolvedValue({ ...SUMMARY, results: [] })
    renderDashboard()
    await waitFor(() => {
      expect(
        screen.getByText(/no data available/i)
      ).toBeInTheDocument()
    })
  })

  it('displays the demonstration data disclaimer', async () => {
    renderDashboard()
    await waitFor(() => {
      expect(
        screen.getByText(/demonstration data/i)
      ).toBeInTheDocument()
    })
  })
})
