/**
 * MappingEditor.test.jsx
 *
 * Focused tests for the MappingEditor component and the mapping_required /
 * mapping_editing states of ImportPage.
 *
 * Tests:
 * 1.  mapping_required state renders MappingEditor
 * 2.  required target fields are rendered
 * 3.  optional source_name field is rendered
 * 4.  source column selector works
 * 5.  fixed-value mode works
 * 6.  transformations can be added
 * 7.  transformations can be removed
 * 8.  transformation order can be changed (move up / move down)
 * 9.  client-side validation: required field without source blocks Generate Preview
 * 10. Generate Preview calls mapPreview() with correct payload
 * 11. loading state disables Generate Preview while in-flight
 * 12. backend error is displayed after mapPreview() failure
 * 13. Reset mappings clears all field values
 * 14. Back to file selection resets to idle
 * 15. canonical direct flow unchanged (regression)
 */

import React from 'react'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import ImportPage from '../pages/ImportPage'
import * as api from '../services/api'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user:            { id: '1', email: 'admin@example.com', role: 'ADMIN', full_name: 'Admin User' },
    isAuthenticated: true,
    isLoading:       false,
    csrfToken:       'mock-csrf',
    login:           vi.fn(),
    logout:          vi.fn(),
    refreshSession:  vi.fn(),
  }),
  AuthProvider: ({ children }) => children,
}))

vi.mock('../services/api', () => ({
  inspectFile:   vi.fn(),
  importPreview: vi.fn(),
  importConfirm: vi.fn(),
  mapPreview:    vi.fn(),
}))

vi.mock('../hooks/useZambiaGeoJSON', () => ({
  useZambiaGeoJSON: () => ({ geojson: null, loading: false, error: null }),
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const INSPECTION_ARBITRARY = {
  inspection_token: 'insp-tok-orders',
  filename: 'orders.csv',
  source_format: 'csv',
  headers: ['region', 'revenue', 'order_date', 'category'],
  columns: [
    { name: 'region',     inferred_type: 'string',  sample_values: ['Lusaka'],   nullable: false, position: 1 },
    { name: 'revenue',    inferred_type: 'decimal', sample_values: ['2500'],     nullable: false, position: 2 },
    { name: 'order_date', inferred_type: 'date',    sample_values: ['2024-01-15'], nullable: false, position: 3 },
    { name: 'category',   inferred_type: 'string',  sample_values: ['Food'],     nullable: false, position: 4 },
  ],
  direct_schema_match: false,
  suggested_mappings: [],
  warnings: [],
}

const INSPECTION_CANONICAL = {
  inspection_token: 'insp-tok-canonical',
  filename: 'data.csv',
  source_format: 'csv',
  headers: ['province_code', 'indicator_code', 'value', 'reference_year', 'dataset_name'],
  columns: [],
  direct_schema_match: true,
  suggested_mappings: [],
  warnings: [],
}

const PREVIEW_CANONICAL = {
  preview_token: 'tok-canon-1',
  total_rows: 2, valid_rows: 2, invalid_rows: 0,
  duplicate_rows: 0, conflict_rows: 0, can_confirm: true,
  errors: [], total_error_count: 0, errors_truncated: false,
  sample_records: [], conflicts: [],
}

const MAP_PREVIEW_RESPONSE = {
  transformed_rows: [],
  total_preview_rows: 0,
  mapped_column_count: 5,
  original_headers: ['region', 'revenue', 'order_date', 'category'],
  target_fields: ['province_code', 'indicator_code', 'value', 'reference_year', 'dataset_name'],
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderImportPage() {
  return render(
    <MemoryRouter initialEntries={['/import']}>
      <ImportPage />
    </MemoryRouter>
  )
}

function pickFile(name = 'orders.csv', size = 100, type = 'text/csv') {
  const file = new File(['x'.repeat(size)], name, { type })
  const input = document.querySelector('input[type="file"]')
  fireEvent.change(input, { target: { files: [file] } })
  return file
}

async function goToMappingEditor() {
  const user = userEvent.setup()
  api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
  renderImportPage()

  pickFile()
  const uploadBtn = await screen.findByRole('button', { name: /upload/i })
  await user.click(uploadBtn)
  await waitFor(() => {
    expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument()
  })
  return user
}

// ---------------------------------------------------------------------------
// beforeEach
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MappingEditor — rendering (mapping_required state)', () => {
  it('1. renders MappingEditor when direct_schema_match=false', async () => {
    await goToMappingEditor()
    expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument()
  })

  it('2. required target fields are rendered', async () => {
    await goToMappingEditor()
    expect(screen.getByText('Province')).toBeInTheDocument()
    expect(screen.getByText('Indicator')).toBeInTheDocument()
    expect(screen.getByText('Value')).toBeInTheDocument()
    expect(screen.getByText('Reference Year')).toBeInTheDocument()
    expect(screen.getByText('Dataset Name')).toBeInTheDocument()
  })

  it('3. optional source_name field is rendered', async () => {
    await goToMappingEditor()
    expect(screen.getByText('Source Name')).toBeInTheDocument()
  })

  it('shows source column chips from inspection', async () => {
    await goToMappingEditor()
    const chips = screen.getAllByTestId('source-column-chip')
    const texts = chips.map(c => c.textContent)
    expect(texts).toContain('region')
    expect(texts).toContain('revenue')
    expect(texts).toContain('order_date')
  })
})

describe('MappingEditor — source column selector', () => {
  it('4. selecting a source column updates the mapping', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
    renderImportPage()
    pickFile()
    await user.click(await screen.findByRole('button', { name: /upload/i }))
    await waitFor(() => expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument())

    // Find source column select for Province row
    const provinceRow = screen.getByTestId('mapping-row-province_code')
    const select = within(provinceRow).getByLabelText(/source column for province/i)
    await user.selectOptions(select, 'region')
    expect(select.value).toBe('region')
  })
})

describe('MappingEditor — fixed value', () => {
  it('5. switching to fixed value shows a text input', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
    renderImportPage()
    pickFile()
    await user.click(await screen.findByRole('button', { name: /upload/i }))
    await waitFor(() => expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument())

    // Switch Indicator to fixed_value
    const indicatorRow = screen.getByTestId('mapping-row-indicator_code')
    const typeSelect = within(indicatorRow).getByLabelText(/source type for indicator/i)
    await user.selectOptions(typeSelect, 'fixed_value')

    const fixedInput = within(indicatorRow).getByLabelText(/fixed value for indicator/i)
    expect(fixedInput).toBeInTheDocument()

    await user.type(fixedInput, 'ECOM_REVENUE')
    expect(fixedInput.value).toBe('ECOM_REVENUE')
  })
})

describe('MappingEditor — transformations', () => {
  it('6. adding a transformation appends it to the list', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
    renderImportPage()
    pickFile()
    await user.click(await screen.findByRole('button', { name: /upload/i }))
    await waitFor(() => expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument())

    const valueRow = screen.getByTestId('mapping-row-value')
    const addSelect = within(valueRow).getByLabelText(/add transformation for value/i)
    await user.selectOptions(addSelect, 'trim')

    expect(within(valueRow).getByText('Trim whitespace')).toBeInTheDocument()
  })

  it('7. removing a transformation removes it from the list', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
    renderImportPage()
    pickFile()
    await user.click(await screen.findByRole('button', { name: /upload/i }))
    await waitFor(() => expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument())

    const valueRow = screen.getByTestId('mapping-row-value')
    // Add trim
    await user.selectOptions(within(valueRow).getByLabelText(/add transformation for value/i), 'trim')
    expect(within(valueRow).getByText('Trim whitespace')).toBeInTheDocument()

    // Remove it
    const removeBtn = within(valueRow).getByLabelText(/remove trim/i)
    await user.click(removeBtn)

    expect(within(valueRow).queryAllByRole('listitem')).toHaveLength(0)
  })

  it('8. transformations can be reordered with move up/down buttons', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
    renderImportPage()
    pickFile()
    await user.click(await screen.findByRole('button', { name: /upload/i }))
    await waitFor(() => expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument())

    const valueRow = screen.getByTestId('mapping-row-value')
    const addSelect = within(valueRow).getByLabelText(/add transformation for value/i)

    // Add trim then parse_number
    await user.selectOptions(addSelect, 'trim')
    await user.selectOptions(addSelect, 'parse_number')

    // Both appear — trim first, then parse_number
    const chips = within(valueRow).getAllByRole('listitem')
    expect(chips[0].textContent).toContain('Trim whitespace')
    expect(chips[1].textContent).toContain('Parse number')

    // Move parse_number up
    const moveUpBtn = within(chips[1]).getByLabelText('Move parse_number up')
    await user.click(moveUpBtn)

    const reorderedChips = within(valueRow).getAllByRole('listitem')
    expect(reorderedChips[0].textContent).toContain('Parse number')
    expect(reorderedChips[1].textContent).toContain('Trim whitespace')
  })
})

describe('MappingEditor — client-side validation', () => {
  it('9. Generate Preview is disabled when required fields are missing sources', async () => {
    await goToMappingEditor()
    // No mappings configured yet — all required fields are empty
    const previewBtn = screen.getByRole('button', { name: /generate preview/i })
    expect(previewBtn).toBeDisabled()
  })
})

describe('MappingEditor — Generate Preview', () => {
  it('10. calls mapPreview() with correct inspection_token and mapping_config', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
    api.mapPreview.mockResolvedValueOnce(MAP_PREVIEW_RESPONSE)
    renderImportPage()
    pickFile()
    await user.click(await screen.findByRole('button', { name: /upload/i }))
    await waitFor(() => expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument())

    // Configure all five required fields with fixed values (simplest valid config)
    const targets = ['province_code', 'indicator_code', 'value', 'reference_year', 'dataset_name']
    const values  = ['LK', 'ECOM', '100', '2024', 'Test DS']

    for (let i = 0; i < targets.length; i++) {
      const row = screen.getByTestId(`mapping-row-${targets[i]}`)
      await user.selectOptions(within(row).getByLabelText(new RegExp(`source type for`, 'i')), 'fixed_value')
      const input = within(row).getByLabelText(new RegExp(`fixed value for`, 'i'))
      await user.clear(input)
      await user.type(input, values[i])
    }

    const previewBtn = screen.getByRole('button', { name: /generate preview/i })
    await user.click(previewBtn)

    await waitFor(() => {
      expect(api.mapPreview).toHaveBeenCalledTimes(1)
    })
    const [calledToken, calledConfig] = api.mapPreview.mock.calls[0]
    expect(calledToken).toBe('insp-tok-orders')
    expect(calledConfig.mapping_version).toBe(1)
    expect(calledConfig.mappings).toHaveLength(5)
    // All must be fixed_value type
    calledConfig.mappings.forEach(m => {
      expect(m.source_type).toBe('fixed_value')
    })
  })

  it('11. Generate Preview button shows loading state while request is in-flight', async () => {
    let resolve
    api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
    api.mapPreview.mockReturnValueOnce(new Promise(r => { resolve = r }))

    const user = userEvent.setup()
    renderImportPage()
    pickFile()
    await user.click(await screen.findByRole('button', { name: /upload/i }))
    await waitFor(() => expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument())

    // Fill all required fields with fixed values
    const targets = ['province_code', 'indicator_code', 'value', 'reference_year', 'dataset_name']
    for (const t of targets) {
      const row = screen.getByTestId(`mapping-row-${t}`)
      await user.selectOptions(within(row).getByLabelText(/source type for/i), 'fixed_value')
      const input = within(row).getByLabelText(/fixed value for/i)
      await user.type(input, 'x')
    }

    const previewBtn = screen.getByRole('button', { name: /generate preview/i })
    await user.click(previewBtn)

    // While in-flight, button should be disabled
    await waitFor(() => {
      expect(previewBtn).toBeDisabled()
    })

    // Clean up
    resolve(MAP_PREVIEW_RESPONSE)
  })

  it('12. backend error is displayed after mapPreview() failure', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
    api.mapPreview.mockRejectedValueOnce(
      Object.assign(new Error('Source column "missing" not found'), {
        response: {
          status: 422,
          data: {
            detail: {
              code: 'IMPORT_SOURCE_COLUMN_NOT_FOUND',
              message: 'Source column "missing" not found in the uploaded file.',
              details: {},
            },
          },
        },
      })
    )
    renderImportPage()
    pickFile()
    await user.click(await screen.findByRole('button', { name: /upload/i }))
    await waitFor(() => expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument())

    // Fill required fields
    const targets = ['province_code', 'indicator_code', 'value', 'reference_year', 'dataset_name']
    for (const t of targets) {
      const row = screen.getByTestId(`mapping-row-${t}`)
      await user.selectOptions(within(row).getByLabelText(/source type for/i), 'fixed_value')
      const input = within(row).getByLabelText(/fixed value for/i)
      await user.type(input, 'x')
    }

    await user.click(screen.getByRole('button', { name: /generate preview/i }))

    await waitFor(() => {
      expect(screen.getByTestId('mapping-error-banner')).toBeInTheDocument()
    })
    expect(screen.getByTestId('mapping-error-banner').textContent).toContain('not found')
  })
})

describe('MappingEditor — reset and navigation', () => {
  it('13. Reset mappings clears all field values', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
    renderImportPage()
    pickFile()
    await user.click(await screen.findByRole('button', { name: /upload/i }))
    await waitFor(() => expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument())

    // Set a value on province_code
    const provinceRow = screen.getByTestId('mapping-row-province_code')
    await user.selectOptions(within(provinceRow).getByLabelText(/source type for province/i), 'fixed_value')
    const input = within(provinceRow).getByLabelText(/fixed value for province/i)
    await user.type(input, 'LK')
    expect(input.value).toBe('LK')

    // Click Reset mappings
    await user.click(screen.getByRole('button', { name: /reset mappings/i }))

    // The row should now be back to 'column' source type with empty value
    await waitFor(() => {
      const resetRow = screen.getByTestId('mapping-row-province_code')
      const typeSelect = within(resetRow).getByLabelText(/source type for province/i)
      expect(typeSelect.value).toBe('column')
    })
  })

  it('14. Back to file selection resets page to idle', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
    renderImportPage()
    pickFile()
    await user.click(await screen.findByRole('button', { name: /upload/i }))
    await waitFor(() => expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /back to file selection/i }))

    await waitFor(() => {
      // After reset, the DropZone should be visible again
      expect(screen.getByRole('region', { name: /csv file upload area/i })).toBeInTheDocument()
    })
    // MappingEditor should be gone
    expect(screen.queryByLabelText(/column mapping editor/i)).not.toBeInTheDocument()
  })
})

describe('MappingEditor — regression', () => {
  it('15. canonical direct flow is unchanged after MappingEditor is added', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_CANONICAL)
    api.importPreview.mockResolvedValueOnce(PREVIEW_CANONICAL)
    renderImportPage()

    pickFile('canonical.csv')
    await user.click(await screen.findByRole('button', { name: /upload/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /confirm import/i })).toBeInTheDocument()
    })
    // No MappingEditor should appear for canonical files
    expect(screen.queryByLabelText(/column mapping editor/i)).not.toBeInTheDocument()
  })
})
