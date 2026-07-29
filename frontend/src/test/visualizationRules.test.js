import { describe, it, expect } from 'vitest'
import { getVisualizationCompatibility } from '../features/analytics/visualization/visualizationRules'

const aggregateResult = {
  columns: [
    { identifier: 'total_revenue', label: 'Total Revenue', role: 'measure', data_type: 'INTEGER', aggregation: 'SUM' },
  ],
  rows: [{ total_revenue: 1250 }],
  row_count: 1,
}

const barResult = {
  columns: [
    { identifier: 'region', label: 'Region', role: 'dimension', data_type: 'TEXT' },
    { identifier: 'revenue_sum', label: 'Revenue', role: 'measure', data_type: 'INTEGER', aggregation: 'SUM' },
  ],
  rows: [
    { region: 'North', revenue_sum: 5000 },
    { region: 'South', revenue_sum: 3000 },
  ],
  row_count: 2,
}

const lineResult = {
  columns: [
    { identifier: 'month', label: 'Month', role: 'dimension', data_type: 'DATE' },
    { identifier: 'revenue_sum', label: 'Revenue', role: 'measure', data_type: 'INTEGER', aggregation: 'SUM' },
  ],
  rows: [
    { month: '2024-01-01', revenue_sum: 1000 },
    { month: '2024-02-01', revenue_sum: 1200 },
  ],
  row_count: 2,
}

describe('visualization compatibility rules', () => {
  it('recommends KPI cards for aggregate-only results', () => {
    const compatibility = getVisualizationCompatibility(aggregateResult)
    expect(compatibility.recommendedChart).toBe('kpi')
    expect(compatibility.supportedChartTypes).toContain('kpi')
    expect(compatibility.recommendation).toMatch(/KPI/i)
  })

  it('recommends bar chart for category plus measure results', () => {
    const compatibility = getVisualizationCompatibility(barResult)
    expect(compatibility.recommendedChart).toBe('bar')
    expect(compatibility.supportedChartTypes).toContain('bar')
  })

  it('recommends line chart for time-series results', () => {
    const compatibility = getVisualizationCompatibility(lineResult)
    expect(compatibility.recommendedChart).toBe('line')
    expect(compatibility.supportedChartTypes).toContain('line')
  })

  it('rejects pie charts for negative or unsupported shapes', () => {
    const negativePie = {
      columns: [
        { identifier: 'region', label: 'Region', role: 'dimension', data_type: 'TEXT' },
        { identifier: 'revenue_sum', label: 'Revenue', role: 'measure', data_type: 'INTEGER', aggregation: 'SUM' },
      ],
      rows: [
        { region: 'North', revenue_sum: -10 },
        { region: 'South', revenue_sum: 20 },
      ],
      row_count: 2,
    }

    const compatibility = getVisualizationCompatibility(negativePie)
    expect(compatibility.supportedChartTypes).not.toContain('pie')
  })

  it('returns no supported charts for empty result sets', () => {
    const compatibility = getVisualizationCompatibility({ columns: [], rows: [], row_count: 0 })
    expect(compatibility.supportedChartTypes).toEqual([])
    expect(compatibility.recommendedChart).toBe(null)
  })
})
