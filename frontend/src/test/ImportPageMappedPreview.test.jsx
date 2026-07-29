import React from 'react'
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import ImportPage from '../pages/ImportPage'
import * as api from '../services/api'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'admin@example.com', role: 'ADMIN', full_name: 'Admin User' },
    isAuthenticated: true,
    isLoading: false,
    csrfToken: 'mock-csrf',
    login: vi.fn(),
    logout: vi.fn(),
    refreshSession: vi.fn(),
  }),
  AuthProvider: ({ children }) => children,
}))

vi.mock('../services/api', () => ({
  inspectFile: vi.fn(),
  importPreview: vi.fn(),
  importConfirm: vi.fn(),
  mapPreview: vi.fn(),
}))

vi.mock('../hooks/useZambiaGeoJSON', () => ({
  useZambiaGeoJSON: () => ({ geojson: null, loading: false, error: null }),
}))

const INSPECTION = {
  inspection_token: 'insp-tok-preview',
  filename: 'orders.csv',
  source_format: 'csv',
  headers: ['region', 'revenue', 'order_date', 'category'],
  columns: [
    { name: 'region', inferred_type: 'string', sample_values: ['Lusaka'], nullable: false, position: 1 },
    { name: 'revenue', inferred_type: 'decimal', sample_values: ['2500'], nullable: false, position: 2 },
    { name: 'order_date', inferred_type: 'date', sample_values: ['2024-01-15'], nullable: false, position: 3 },
    { name: 'category', inferred_type: 'string', sample_values: ['Food'], nullable: false, position: 4 },
  ],
  direct_schema_match: false,
  suggested_mappings: [],
  warnings: [],
}

const MAP_PREVIEW_RESPONSE = {
  transformed_rows: [
    { province_code: 'LUS', indicator_code: 'REV', value: '2500', reference_year: '2024', dataset_name: 'Sales' },
  ],
  total_preview_rows: 1,
  mapped_column_count: 5,
  original_headers: ['region', 'revenue', 'order_date', 'category'],
  target_fields: ['province_code', 'indicator_code', 'value', 'reference_year', 'dataset_name'],
}

function renderImportPage() {
  return render(
    <MemoryRouter initialEntries={['/import']}>
      <ImportPage />
    </MemoryRouter>
  )
}

async function configureRequiredMappings(user, valuesByTarget = {
  province_code: 'LUS',
  indicator_code: 'REV',
  value: '2500',
  reference_year: '2024',
  dataset_name: 'Sales',
}) {
  const targets = Object.keys(valuesByTarget)
  for (const target of targets) {
    const row = screen.getByTestId(`mapping-row-${target}`)
    await user.selectOptions(within(row).getByLabelText(/source type for/i), 'fixed_value')
    await user.type(within(row).getByLabelText(/fixed value for/i), valuesByTarget[target])
  }
}

function pickFile(name = 'orders.csv', size = 100, type = 'text/csv') {
  const file = new File(['x'.repeat(size)], name, { type })
  const input = document.querySelector('input[type="file"]')
  fireEvent.change(input, { target: { files: [file] } })
  return file
}

async function openMappingEditor() {
  const user = userEvent.setup()
  api.inspectFile.mockResolvedValueOnce(INSPECTION)
  renderImportPage()
  pickFile()
  await user.click(await screen.findByRole('button', { name: /upload/i }))
  await waitFor(() => expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument())
  return user
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ImportPage mapped preview', () => {
  it('shows the mapped preview state after a successful mapPreview call', async () => {
    const user = await openMappingEditor()
    await configureRequiredMappings(user)
    api.mapPreview.mockResolvedValueOnce(MAP_PREVIEW_RESPONSE)
    await user.click(screen.getByRole('button', { name: /generate preview/i }))

    await waitFor(() => {
      expect(screen.getByText(/mapped preview/i)).toBeInTheDocument()
    })
  })

  it('renders transformed rows and preview metadata', async () => {
    const user = await openMappingEditor()
    await configureRequiredMappings(user)
    api.mapPreview.mockResolvedValueOnce(MAP_PREVIEW_RESPONSE)
    await user.click(screen.getByRole('button', { name: /generate preview/i }))

    await waitFor(() => {
      expect(screen.getByText('LUS')).toBeInTheDocument()
      expect(screen.getByText(/Total preview rows/i)).toBeInTheDocument()
      expect(screen.getByText(/Mapped columns/i)).toBeInTheDocument()
      expect(screen.getByText(/Original headers/i)).toBeInTheDocument()
      expect(screen.getByText(/Target fields/i)).toBeInTheDocument()
    })
  })

  it('preserves the original file name in the mapped preview state', async () => {
    const user = await openMappingEditor()
    await configureRequiredMappings(user)
    api.mapPreview.mockResolvedValueOnce(MAP_PREVIEW_RESPONSE)
    await user.click(screen.getByRole('button', { name: /generate preview/i }))

    await waitFor(() => {
      expect(screen.getByText(/orders\.csv/i)).toBeInTheDocument()
    })
  })

  it('renders an empty state cleanly when there are no transformed rows', async () => {
    const user = await openMappingEditor()
    await configureRequiredMappings(user)
    api.mapPreview.mockResolvedValueOnce({ ...MAP_PREVIEW_RESPONSE, transformed_rows: [] })
    await user.click(screen.getByRole('button', { name: /generate preview/i }))

    await waitFor(() => {
      expect(screen.getByText(/no transformed rows/i)).toBeInTheDocument()
    })
  })

  it('returns to the mapping editor and preserves the mapping configuration', async () => {
    const user = await openMappingEditor()
    await configureRequiredMappings(user)

    api.mapPreview.mockResolvedValueOnce(MAP_PREVIEW_RESPONSE)
    await user.click(screen.getByRole('button', { name: /generate preview/i }))
    await waitFor(() => expect(screen.getByText(/mapped preview/i)).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /back to mapping/i }))
    await waitFor(() => expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument())

    const restoredRow = screen.getByTestId('mapping-row-province_code')
    expect(within(restoredRow).getByLabelText(/source type for province/i).value).toBe('fixed_value')
    expect(within(restoredRow).getByLabelText(/fixed value for province/i).value).toBe('LUS')
  })

  it('does not re-inspect the file when going back to mapping', async () => {
    const user = await openMappingEditor()
    await configureRequiredMappings(user)
    api.mapPreview.mockResolvedValueOnce(MAP_PREVIEW_RESPONSE)
    await user.click(screen.getByRole('button', { name: /generate preview/i }))
    await waitFor(() => expect(screen.getByText(/mapped preview/i)).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /back to mapping/i }))
    expect(api.inspectFile).toHaveBeenCalledTimes(1)
  })

  it('shows a disabled confirm import action for mapped preview', async () => {
    const user = await openMappingEditor()
    await configureRequiredMappings(user)
    api.mapPreview.mockResolvedValueOnce(MAP_PREVIEW_RESPONSE)
    await user.click(screen.getByRole('button', { name: /generate preview/i }))

    await waitFor(() => {
      const button = screen.getByRole('button', { name: /confirm import/i })
      expect(button).toBeDisabled()
    })
  })

  it('renders backend errors without changing their structure', async () => {
    const user = await openMappingEditor()
    await configureRequiredMappings(user)
    api.mapPreview.mockRejectedValueOnce(
      Object.assign(new Error('bad mapping'), {
        response: {
          status: 422,
          data: {
            detail: {
              code: 'IMPORT_VALIDATION_FAILED',
              message: 'The mapping is invalid.',
              details: { field: 'province_code' },
            },
          },
        },
      })
    )
    await user.click(screen.getByRole('button', { name: /generate preview/i }))

    await waitFor(() => {
      expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument()
    })
    expect(screen.getByTestId('mapping-error-banner').textContent).toContain('The mapping is invalid.')
  })
})
