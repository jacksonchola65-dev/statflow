import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../features/analytics/visualization/BarVisualization', () => ({
  default: () => {
    throw new Error('render failed')
  },
}))

import AnalyticsVisualization from '../features/analytics/visualization/AnalyticsVisualization'

const chartResult = {
  columns: [
    { identifier: 'region', label: 'Region', role: 'dimension', data_type: 'TEXT' },
    { identifier: 'revenue', label: 'Revenue', role: 'measure', data_type: 'INTEGER', aggregation: 'SUM' },
  ],
  rows: [
    { region: 'North', revenue: 1200 },
    { region: 'South', revenue: 900 },
  ],
  row_count: 2,
}

describe('AnalyticsVisualization', () => {
  it('renders an accessible summary for the selected visualization result', () => {
    render(<AnalyticsVisualization result={chartResult} chartType="bar" />)

    expect(screen.getByRole('heading', { name: /visualization result/i })).toBeInTheDocument()
    expect(screen.getByText(/rows shown: 2/i)).toBeInTheDocument()
    expect(screen.getByText(/accessible summary/i)).toBeInTheDocument()
  })

  it('shows a localized fallback when the chart renderer throws', () => {
    render(<AnalyticsVisualization result={chartResult} chartType="bar" />)

    expect(screen.getByText(/visualization could not be rendered/i)).toBeInTheDocument()
    expect(screen.getByText(/table view remains available/i)).toBeInTheDocument()
  })
})
