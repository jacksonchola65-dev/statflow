import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: true, isLoading: false, user: { role: 'ANALYST' } }),
}))

vi.mock('../services/analyticsApi', () => ({
  getDatasetIntelligence: vi.fn(),
}))

import * as analyticsApi from '../services/analyticsApi'
import DatasetIntelligencePage from '../pages/DatasetIntelligencePage'

const BASE_RESULT = {
  dataset: { id: 'dataset-1', name: 'Sales', row_count: 3, column_count: 3 },
  analysis_scope: 'FULL_DATASET',
  sample_size: 3,
  total_rows: 3,
  coverage_ratio: 1,
  kpis: [{ id: 'kpi-1', label: 'Total Revenue', value: 125000, unit: 'USD' }],
  visualizations: [{
    id: 'table-1', type: 'table', title: 'Sales table', reason_code: 'table_fallback',
    data: [{ Product: 'A', Revenue: 100 }], analysis_scope: 'PREVIEW', sample_size: 1, total_rows: 3,
  }],
  insights: [{ id: 'insight-1', subject: 'Maximum value in Revenue', value: 125000, analysis_scope: 'FULL_DATASET' }],
  quality_notes: [{ id: 'quality-1', observation: 'No missing values.', severity: 'info' }],
  provenance: { source: 'stored_dataset', aggregation_authority: 'AnalyticsRepository' },
  warnings: [],
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/analytics/datasets/dataset-1']}>
      <Routes><Route path="/analytics/datasets/:datasetId" element={<DatasetIntelligencePage />} /></Routes>
    </MemoryRouter>,
  )
}

describe('DatasetIntelligencePage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('announces loading and renders the dataset intelligence contract', async () => {
    analyticsApi.getDatasetIntelligence.mockResolvedValueOnce(BASE_RESULT)
    renderPage()
    expect(screen.getByText(/Analyzing dataset/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Sales' })).toBeInTheDocument())
    expect(screen.getByText('Total Revenue')).toBeInTheDocument()
    expect(screen.getByText('Recommended visualizations')).toBeInTheDocument()
    expect(screen.getByText('Insights')).toBeInTheDocument()
    expect(screen.getByText('Maximum value in Revenue: 125,000')).toBeInTheDocument()
    expect(screen.getByText('No missing values.')).toBeInTheDocument()
    expect(screen.getByText('How this was calculated')).toBeInTheDocument()
    expect(screen.getByText('Provenance')).toBeInTheDocument()
  })

  it('renders a controlled table fallback and does not invent a map', async () => {
    analyticsApi.getDatasetIntelligence.mockResolvedValueOnce(BASE_RESULT)
    renderPage()
    await screen.findByRole('table', { name: 'Sales table' })
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.queryByText(/map/i)).not.toBeInTheDocument()
  })

  it('renders valid area and pie artifact contracts', async () => {
    analyticsApi.getDatasetIntelligence.mockResolvedValueOnce({
      ...BASE_RESULT,
      visualizations: [
        {
          id: 'area-1', type: 'area', title: 'Revenue area', reason_code: 'time_series_measure',
          dimension: { column: 'date', label: 'Date' }, measure: { column: 'value', aggregation: 'SUM', unit: '' },
          data: [{ date: '2025-01-01', value: 10 }, { date: '2025-02-01', value: 20 }], analysis_scope: 'FULL_DATASET', total_rows: 2,
        },
        {
          id: 'pie-1', type: 'pie', title: 'Revenue share', reason_code: 'part_to_whole',
          dimension: { column: 'product', label: 'Product' }, measure: { column: 'value', aggregation: 'SUM', unit: '' },
          data: [{ product: 'A', value: 10 }, { product: 'B', value: 20 }], analysis_scope: 'FULL_DATASET', total_rows: 2,
        },
      ],
    })
    renderPage()
    expect(await screen.findByText('Revenue area')).toBeInTheDocument()
    expect(screen.getByText('Revenue share')).toBeInTheDocument()
  })

  it('renders a user-readable API error', async () => {
    analyticsApi.getDatasetIntelligence.mockRejectedValueOnce({ detail: 'Dataset not found.' })
    renderPage()
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Dataset not found.'))
  })
})
