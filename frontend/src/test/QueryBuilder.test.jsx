import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AnalyticsPage from '../pages/AnalyticsPage'
import * as analyticsApi from '../services/analyticsApi'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: { id: '1', email: 'user@example.com', role: 'ANALYST', full_name: 'Analyst User' },
    isAuthenticated: true,
    isLoading: false,
    csrfToken: 'mock-csrf',
    login: vi.fn(),
    logout: vi.fn(),
    refreshSession: vi.fn(),
  })),
  AuthProvider: ({ children }) => children,
}))

vi.mock('../services/analyticsApi')

const mockDatasets = [
  {
    ingestion_job_id: 'job-1',
    dataset_name: 'Sales',
    source_name: 'CRM',
    row_count: 1000,
    column_count: 10,
    status: 'COMPLETED',
    completed_at: '2024-01-15T10:00:00Z',
    created_at: '2024-01-15T09:00:00Z',
  },
]

const mockDimensions = [
  { identifier: 'region', display_name: 'Region', data_type: 'TEXT' },
  { identifier: 'product', display_name: 'Product', data_type: 'TEXT' },
]

const mockMeasures = [
  { identifier: 'revenue', display_name: 'Revenue', data_type: 'INTEGER', supported_aggregations: ['SUM', 'AVERAGE'] },
  { identifier: 'units', display_name: 'Units', data_type: 'INTEGER', supported_aggregations: ['SUM', 'COUNT', 'AVERAGE'] },
]

const mockQueryResult = {
  ingestion_job_id: 'job-1',
  columns: [
    { identifier: 'region', label: 'Region', role: 'dimension', data_type: 'TEXT' },
    { identifier: 'revenue_sum', label: 'Sum of revenue', role: 'measure', aggregation: 'SUM', data_type: 'INTEGER' },
  ],
  rows: [
    { region: 'North', revenue_sum: 5000 },
    { region: 'South', revenue_sum: 3000 },
  ],
  row_count: 2,
  limit: 100,
  offset: 0,
  has_more: false,
}

describe('AnalyticsPage Query Builder Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    analyticsApi.listAnalyticsDatasets.mockResolvedValue({
      items: mockDatasets,
      total: 1,
      limit: 10,
      offset: 0,
      has_more: false,
    })
    analyticsApi.getDatasetDetails.mockResolvedValue({
      summary: mockDatasets[0],
      columns: [],
      available_dimensions: mockDimensions,
      available_measures: mockMeasures,
      preview_available: true,
      analytics_ready: true,
    })
    analyticsApi.getDatasetSchema.mockResolvedValue([])
    analyticsApi.getDatasetDimensions.mockResolvedValue(mockDimensions)
    analyticsApi.getDatasetMeasures.mockResolvedValue(mockMeasures)
    analyticsApi.getDatasetPreview.mockResolvedValue({
      ingestion_job_id: 'job-1',
      columns: [],
      rows: [],
      limit: 10,
      returned_count: 0,
    })
    analyticsApi.getDatasetStatistics.mockResolvedValue({
      ingestion_job_id: 'job-1',
      row_count: 1000,
      column_count: 10,
      nullable_column_count: 2,
      numeric_column_count: 5,
      text_column_count: 3,
      date_column_count: 1,
      datetime_column_count: 0,
      boolean_column_count: 1,
      completed_at: '2024-01-15T10:00:00Z',
    })
    analyticsApi.executeAnalyticsQuery.mockResolvedValue(mockQueryResult)
  })

  it('should render query builder when dataset is selected and query tab is active', async () => {
    render(
      <MemoryRouter>
        <AnalyticsPage />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /sales/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /sales/i }))

    await waitFor(() => {
      const queryTab = screen.getByText('Query Builder')
      expect(queryTab).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Query Builder'))

    await waitFor(() => {
      expect(screen.getByText(/Build and run an analytics query/)).toBeInTheDocument()
    })

    expect(screen.getByText(/Select zero or more dimensions to group results by/)).toBeInTheDocument()
    expect(screen.getByText(/Add one or more measures/)).toBeInTheDocument()
  })

  it('should show error when query execution fails', async () => {
    analyticsApi.executeAnalyticsQuery.mockRejectedValue({
      detail: 'Query validation failed',
    })

    render(
      <MemoryRouter>
        <AnalyticsPage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByRole('button', { name: /sales/i })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /sales/i }))

    await waitFor(() => {
      fireEvent.click(screen.getByText('Query Builder'))
    })

    const runButton = await screen.findByText('Run query')
    fireEvent.click(runButton)

    // Check that error detail text is shown
    await waitFor(() => {
      expect(screen.getByText('Query validation failed')).toBeInTheDocument()
    }, { timeout: 5000 })
  })
})
