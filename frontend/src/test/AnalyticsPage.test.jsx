import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach } from 'vitest'

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

vi.mock('../services/analyticsApi', () => ({
  listAnalyticsDatasets: vi.fn(),
  getDatasetDetails: vi.fn(),
  getDatasetSchema: vi.fn(),
  getDatasetDimensions: vi.fn(),
  getDatasetMeasures: vi.fn(),
  getDatasetPreview: vi.fn(),
  getDatasetStatistics: vi.fn(),
}))

import * as AuthContext from '../contexts/AuthContext'
import * as analyticsApi from '../services/analyticsApi'
import AnalyticsPage from '../pages/AnalyticsPage'
import AppRouter from '../app/router'

const DATASET_A = {
  ingestion_job_id: 'dataset-a',
  source_name: 'Source A',
  dataset_name: 'Dataset A',
  status: 'COMPLETED',
  row_count: 5,
  column_count: 2,
  completed_at: '2026-01-01T00:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
  description: 'First dataset',
}

const DATASET_B = {
  ingestion_job_id: 'dataset-b',
  source_name: 'Source B',
  dataset_name: 'Dataset B',
  status: 'COMPLETED',
  row_count: 3,
  column_count: 1,
  completed_at: '2026-01-02T00:00:00Z',
  created_at: '2026-01-02T00:00:00Z',
  description: 'Second dataset',
}

function renderAnalyticsPage(initialEntries = ['/analytics']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AnalyticsPage />
    </MemoryRouter>,
  )
}

function renderAnalyticsRoute(initialEntries = ['/analytics']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AppRouter />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AnalyticsPage', () => {
  it('renders the protected analytics route for authenticated users', async () => {
    analyticsApi.listAnalyticsDatasets.mockResolvedValueOnce({
      items: [],
      total: 0,
      limit: 10,
      offset: 0,
      has_more: false,
    })

    renderAnalyticsRoute()

    await waitFor(() => expect(screen.getByText(/Analytics Workspace/i)).toBeInTheDocument())
  })

  it('redirects unauthenticated users to login', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      csrfToken: null,
      login: vi.fn(),
      logout: vi.fn(),
      refreshSession: vi.fn(),
    })

    renderAnalyticsRoute()

    await waitFor(() => expect(screen.getByText(/Sign in to your account/i)).toBeInTheDocument())
  })

  it('filters visible datasets only on the loaded page', async () => {
    analyticsApi.listAnalyticsDatasets.mockResolvedValueOnce({
      items: [DATASET_A, DATASET_B],
      total: 2,
      limit: 10,
      offset: 0,
      has_more: false,
    })
    analyticsApi.getDatasetDetails.mockResolvedValue({ summary: DATASET_A, columns: [], available_dimensions: [], available_measures: [], preview_available: true, analytics_ready: true })
    analyticsApi.getDatasetStatistics.mockResolvedValue({ ingestion_job_id: 'dataset-a', row_count: 5, column_count: 2, nullable_column_count: 0, numeric_column_count: 0, text_column_count: 0, date_column_count: 0, datetime_column_count: 0, boolean_column_count: 0, completed_at: '2026-01-01T00:00:00Z' })
    analyticsApi.getDatasetSchema.mockResolvedValue([])
    analyticsApi.getDatasetDimensions.mockResolvedValue([])
    analyticsApi.getDatasetMeasures.mockResolvedValue([])
    analyticsApi.getDatasetPreview.mockResolvedValue({ ingestion_job_id: 'dataset-a', columns: ['region'], rows: [], limit: 10, returned_count: 0 })

    renderAnalyticsPage()

    await waitFor(() => expect(screen.getByText('Dataset A')).toBeInTheDocument())

    await userEvent.type(screen.getByRole('searchbox'), 'Dataset B')

    expect(await screen.findByRole('button', { name: /Dataset B/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Dataset A/i })).not.toBeInTheDocument()
    expect(screen.getByText(/currently loaded page only/i)).toBeInTheDocument()
  })

  it('shows dataset details, statistics, and preview after selecting a dataset', async () => {
    analyticsApi.listAnalyticsDatasets.mockResolvedValueOnce({
      items: [DATASET_A],
      total: 1,
      limit: 10,
      offset: 0,
      has_more: false,
    })
    analyticsApi.getDatasetDetails.mockResolvedValueOnce({
      summary: DATASET_A,
      columns: [
        { identifier: 'region', display_name: 'Region', inferred_type: 'TEXT', nullable: false, ordinal_position: 0, semantic_role: null, dimension_eligible: true, measure_eligible: false, supported_aggregations: ['COUNT', 'COUNT_DISTINCT'] },
      ],
      available_dimensions: [{ identifier: 'region', display_name: 'Region', data_type: 'TEXT' }],
      available_measures: [],
      preview_available: true,
      analytics_ready: true,
    })
    analyticsApi.getDatasetStatistics.mockResolvedValueOnce({
      ingestion_job_id: 'dataset-a',
      row_count: 5,
      column_count: 2,
      nullable_column_count: 0,
      numeric_column_count: 0,
      text_column_count: 1,
      date_column_count: 0,
      datetime_column_count: 0,
      boolean_column_count: 0,
      completed_at: '2026-01-01T00:00:00Z',
    })
    analyticsApi.getDatasetSchema.mockResolvedValueOnce([
      { identifier: 'region', display_name: 'Region', inferred_type: 'TEXT', nullable: false, ordinal_position: 0, semantic_role: null, dimension_eligible: true, measure_eligible: false, supported_aggregations: ['COUNT', 'COUNT_DISTINCT'] },
    ])
    analyticsApi.getDatasetDimensions.mockResolvedValueOnce([{ identifier: 'region', display_name: 'Region', data_type: 'TEXT' }])
    analyticsApi.getDatasetMeasures.mockResolvedValueOnce([])
    analyticsApi.getDatasetPreview.mockResolvedValueOnce({ ingestion_job_id: 'dataset-a', columns: ['region'], rows: [{ region: 'North' }], limit: 10, returned_count: 1 })

    renderAnalyticsPage()

    await screen.findByText('Dataset overview')
    expect(screen.getByText('Total rows')).toBeInTheDocument()
    expect(screen.getByText('Total columns')).toBeInTheDocument()

    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())
    expect(screen.getByText('region')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: /preview/i }))
    expect(await screen.findByText('North')).toBeInTheDocument()
  })

  it('preserves the newest selected dataset when older requests resolve later', async () => {
    let resolveA
    let resolveB

    analyticsApi.listAnalyticsDatasets.mockResolvedValueOnce({
      items: [DATASET_A, DATASET_B],
      total: 2,
      limit: 10,
      offset: 0,
      has_more: false,
    })

    analyticsApi.getDatasetDetails.mockImplementation((id) => {
      if (id === 'dataset-a') {
        return new Promise((resolve) => {
          resolveA = resolve
        })
      }
      if (id === 'dataset-b') {
        return new Promise((resolve) => {
          resolveB = resolve
        })
      }
      return Promise.resolve({ summary: id === 'dataset-a' ? DATASET_A : DATASET_B, columns: [], available_dimensions: [], available_measures: [], preview_available: true, analytics_ready: true })
    })

    analyticsApi.getDatasetStatistics.mockResolvedValue({ ingestion_job_id: 'dataset-a', row_count: 5, column_count: 2, nullable_column_count: 0, numeric_column_count: 0, text_column_count: 0, date_column_count: 0, datetime_column_count: 0, boolean_column_count: 0, completed_at: '2026-01-01T00:00:00Z' })
    analyticsApi.getDatasetSchema.mockResolvedValue([])
    analyticsApi.getDatasetDimensions.mockResolvedValue([])
    analyticsApi.getDatasetMeasures.mockResolvedValue([])
    analyticsApi.getDatasetPreview.mockResolvedValue({ ingestion_job_id: 'dataset-a', columns: [], rows: [], limit: 10, returned_count: 0 })

    renderAnalyticsPage()

    await waitFor(() => expect(screen.getByText('Dataset A')).toBeInTheDocument())
    const datasetBButton = screen.getByRole('button', { name: /Dataset B/i })
    await userEvent.click(datasetBButton)

    expect(analyticsApi.getDatasetDetails).toHaveBeenCalledWith('dataset-a', expect.anything())
    expect(analyticsApi.getDatasetDetails).toHaveBeenCalledWith('dataset-b', expect.anything())

    expect(resolveB).toBeDefined()
    resolveB({ summary: DATASET_B, columns: [], available_dimensions: [], available_measures: [], preview_available: true, analytics_ready: true })

    await waitFor(() => expect(screen.getByRole('heading', { name: /Dataset B/i, level: 1 })).toBeInTheDocument())

    resolveA({ summary: DATASET_A, columns: [], available_dimensions: [], available_measures: [], preview_available: true, analytics_ready: true })

    await new Promise((resolve) => setTimeout(resolve, 10))
    expect(screen.getByRole('heading', { name: /Dataset B/i, level: 1 })).toBeInTheDocument()
  })
})
