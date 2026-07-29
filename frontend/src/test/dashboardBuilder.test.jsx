import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DashboardWorkspace from '../features/analytics/dashboard/DashboardWorkspace'
import { dashboardReducer, INITIAL_DASHBOARD } from '../features/analytics/dashboard/dashboardReducer'
import { validateDashboardMetadata } from '../features/analytics/dashboard/dashboardValidation'

const snapshot = {
  title: 'Revenue snapshot',
  subtitle: 'Revenue by region',
  chartType: 'bar',
  result: {
    columns: [
      { identifier: 'region', label: 'Region', role: 'dimension' },
      { identifier: 'revenue', label: 'Revenue', role: 'measure' },
    ],
    rows: [
      { region: 'North', revenue: 1200 },
      { region: 'South', revenue: 900 },
    ],
    row_count: 2,
  },
}

describe('dashboard builder foundation', () => {
  it('creates and validates dashboard metadata in a pure way', () => {
    const dashboard = dashboardReducer(INITIAL_DASHBOARD, { type: 'CREATE' })
    const metadata = validateDashboardMetadata('  Revenue Dashboard  ', '  Overview  ')

    expect(dashboard.title).toBe('Untitled dashboard')
    expect(metadata.normalizedTitle).toBe('Revenue Dashboard')
    expect(metadata.normalizedDescription).toBe('Overview')
  })

  it('adds a visualization card, resizes it, reorders it, and removes it', async () => {
    const user = userEvent.setup()
    render(<DashboardWorkspace snapshot={snapshot} />)

    await user.click(screen.getByRole('button', { name: /add visualization to dashboard/i }))
    expect(screen.getByText(/dashboard metadata panel/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /resize revenue snapshot to large/i }))
    await user.click(screen.getByRole('button', { name: /move revenue snapshot later/i }))
    await user.click(screen.getByRole('button', { name: /remove revenue snapshot/i }))

    expect(screen.getByText(/add a visualization to start building the dashboard/i)).toBeInTheDocument()
  })

  it('toggles preview mode and shows the preview state', async () => {
    const user = userEvent.setup()
    render(<DashboardWorkspace snapshot={snapshot} />)

    await user.click(screen.getByRole('button', { name: /add visualization to dashboard/i }))
    await user.click(screen.getByRole('button', { name: /toggle preview mode/i }))

    expect(screen.getByText(/dashboard preview/i)).toBeInTheDocument()
  })
})
