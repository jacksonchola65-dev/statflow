/**
 * ImportPage.test.jsx
 *
 * Frontend tests for the CSV import flow: idle → previewing → success.
 *
 * References: REQ-10.5, REQ-12.12 – REQ-12.16
 */

import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import ImportPage from '../pages/ImportPage'
import * as api from '../services/api'

// ---------------------------------------------------------------------------
// Mock AuthContext so Topbar (inside AppShell) doesn't need a real provider
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

// ---------------------------------------------------------------------------
// Mock API module
// ---------------------------------------------------------------------------

vi.mock('../services/api', () => ({
  inspectFile: vi.fn(),
  importPreview: vi.fn(),
  importConfirm: vi.fn(),
}))

// Mock useZambiaGeoJSON so it never fires a real fetch in jsdom.
// (Same pattern used by DashboardPage.test.jsx)
vi.mock('../hooks/useZambiaGeoJSON', () => ({
  useZambiaGeoJSON: () => ({ geojson: null, loading: false, error: null }),
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PREVIEW_CAN_CONFIRM = {
  preview_token:     'tok-abc-123',
  total_rows:        3,
  valid_rows:        3,
  invalid_rows:      0,
  duplicate_rows:    0,
  conflict_rows:     0,
  can_confirm:       true,
  errors:            [],
  total_error_count: 0,
  errors_truncated:  false,
  sample_records:    [
    { row_number: 1, province_code: 'CP', indicator_code: 'POVERTY_RATE', value: '55.2', reference_year: 2022, dataset_name: 'Test DS' },
  ],
  conflicts:         [],
}

const PREVIEW_CANNOT_CONFIRM = {
  ...PREVIEW_CAN_CONFIRM,
  can_confirm:    false,
  invalid_rows:   1,
  valid_rows:     2,
  errors: [
    { row_number: 2, column: 'province_code', raw_value: 'XX', message: 'Unknown province code: XX' },
  ],
  total_error_count: 1,
  errors_truncated:  false,
}

const PREVIEW_TRUNCATED_ERRORS = {
  ...PREVIEW_CANNOT_CONFIRM,
  invalid_rows:      110,
  valid_rows:        0,
  can_confirm:       false,
  errors:            Array.from({ length: 100 }, (_, i) => ({
    row_number: i + 1,
    column: 'province_code',
    raw_value: 'XX',
    message: 'Unknown province code: XX',
  })),
  total_error_count: 110,
  errors_truncated:  true,
}

const CONFIRM_RESPONSE = {
  imported_count:   3,
  datasets_created: 1,
  dataset_ids:      ['ds-uuid-1'],
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

/**
 * Simulate the user picking a file by firing a change event on the hidden
 * <input type="file"> element inside the DropZone.
 */
function pickFile(file) {
  const input = document.querySelector('input[type="file"]')
  expect(input).not.toBeNull()
  fireEvent.change(input, { target: { files: [file] } })
}

function makeFile(name, sizeBytes, type = 'text/csv') {
  // Create a real File object with the requested byte size.
  const content = 'x'.repeat(sizeBytes)
  return new File([content], name, { type })
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

describe('ImportPage — client-side file validation (REQ-12.12)', () => {
  it('shows an error and makes no API call when a file > 5 MB is selected', async () => {
    renderImportPage()

    const bigFile = makeFile('big.csv', 5 * 1024 * 1024 + 1, 'text/csv')
    pickFile(bigFile)

    // The DropZone renders the error via role="alert"
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(screen.getByRole('alert').textContent).toMatch(/5 MB size limit/i)

    // Upload button must be disabled — no API call should happen even if clicked
    const uploadBtn = screen.getByRole('button', { name: /upload/i })
    expect(uploadBtn).toBeDisabled()
    expect(api.importPreview).not.toHaveBeenCalled()
  })

  it('accepts a .txt file selection and enables the upload button', async () => {
    renderImportPage()

    const txtFile = makeFile('data.txt', 100, 'text/plain')
    pickFile(txtFile)

    await waitFor(() => {
      expect(screen.queryByRole('alert')).toBeNull()
    })

    const uploadBtn = screen.getByRole('button', { name: /upload/i })
    expect(uploadBtn).not.toBeDisabled()
    expect(api.importPreview).not.toHaveBeenCalled()
  })
})

describe('ImportPage — preview phase (REQ-12.13, REQ-12.14)', () => {
  it('renders summary counts after a successful preview response', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce({ direct_schema_match: true })
    api.importPreview.mockResolvedValueOnce(PREVIEW_CAN_CONFIRM)
    renderImportPage()

    const csvFile = makeFile('data.csv', 100, 'text/csv')
    pickFile(csvFile)

    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    // PreviewSummary should appear with counts
    await waitFor(() => {
      expect(screen.getByLabelText(/import validation summary/i)).toBeInTheDocument()
    })

    // Check count labels rendered by ImportSummary badges
    expect(screen.getByText('Total rows')).toBeInTheDocument()
    expect(screen.getByText('Valid')).toBeInTheDocument()
    expect(screen.getByText('Invalid')).toBeInTheDocument()
    expect(screen.getByText('Duplicates')).toBeInTheDocument()
    expect(screen.getByText('Conflicts')).toBeInTheDocument()

    // total_rows=3 and valid_rows=3 both render as "3" — use getAllByText
    const threes = screen.getAllByText('3')
    expect(threes.length).toBeGreaterThanOrEqual(2)
  })

  it('disables the Confirm Import button when can_confirm=false', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce({ direct_schema_match: true })
    api.importPreview.mockResolvedValueOnce(PREVIEW_CANNOT_CONFIRM)
    renderImportPage()

    pickFile(makeFile('data.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /confirm import/i })).toBeInTheDocument()
    })

    const confirmBtn = screen.getByRole('button', { name: /confirm import/i })
    expect(confirmBtn).toBeDisabled()
  })

  it('enables the Confirm Import button when can_confirm=true', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce({ direct_schema_match: true })
    api.importPreview.mockResolvedValueOnce(PREVIEW_CAN_CONFIRM)
    renderImportPage()

    pickFile(makeFile('data.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /confirm import/i })).toBeInTheDocument()
    })

    const confirmBtn = screen.getByRole('button', { name: /confirm import/i })
    expect(confirmBtn).not.toBeDisabled()
  })
})

describe('ImportPage — success phase (REQ-10.7)', () => {
  it('shows imported_count in the success state after a successful confirm', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce({ direct_schema_match: true })
    api.importPreview.mockResolvedValueOnce(PREVIEW_CAN_CONFIRM)
    api.importConfirm.mockResolvedValueOnce(CONFIRM_RESPONSE)
    renderImportPage()

    pickFile(makeFile('data.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    const confirmBtn = await screen.findByRole('button', { name: /confirm import/i })
    await user.click(confirmBtn)

    // Success state should show the imported count
    await waitFor(() => {
      expect(screen.getByText(/3/)).toBeInTheDocument()
      expect(screen.getByText(/successfully imported into the database/i)).toBeInTheDocument()
    })

    // View Dashboard link should appear
    expect(screen.getByRole('link', { name: /view dashboard/i })).toBeInTheDocument()
  })
})

describe('ImportPage — API error handling (REQ-10.8)', () => {
  it('displays an error message when the preview API returns 422', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce({ direct_schema_match: true })
    api.importPreview.mockRejectedValueOnce(
      new Error('Missing required columns: [value]')
    )
    renderImportPage()

    pickFile(makeFile('data.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    // An error banner (role="alert") should appear with the detail message
    await waitFor(() => {
      const alerts = screen.getAllByRole('alert')
      const messages = alerts.map(a => a.textContent)
      expect(messages.some(msg => /missing required columns/i.test(msg))).toBe(true)
    })
  })

  it('displays a conflict message when the confirm API returns 409', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce({ direct_schema_match: true })
    api.importPreview.mockResolvedValueOnce(PREVIEW_CAN_CONFIRM)
    // importConfirm → throwDetail → new Error(JSON.stringify(detail))
    api.importConfirm.mockRejectedValueOnce(
      new Error(JSON.stringify({
        message: '1 row(s) conflict with existing data.',
        conflicts: [],
      }))
    )
    renderImportPage()

    pickFile(makeFile('data.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    const confirmBtn = await screen.findByRole('button', { name: /confirm import/i })
    await user.click(confirmBtn)

    await waitFor(() => {
      const alerts = screen.getAllByRole('alert')
      const messages = alerts.map(a => a.textContent)
      expect(messages.some(msg => /conflict/i.test(msg))).toBe(true)
    })
  })
})

describe('ImportPage — truncated errors notice (REQ-10.5, REQ-12.16)', () => {
  it('shows the truncation notice when errors_truncated=true', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce({ direct_schema_match: true })
    api.importPreview.mockResolvedValueOnce(PREVIEW_TRUNCATED_ERRORS)
    renderImportPage()

    pickFile(makeFile('data.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    // ValidationErrorTable renders the truncation notice as role="status"
    await waitFor(() => {
      expect(
        screen.getByText(/Showing the first 100 of 110 validation errors\./i)
      ).toBeInTheDocument()
    })
  })
})


// ---------------------------------------------------------------------------
// Task 8A — Inspection flow fixtures
// ---------------------------------------------------------------------------

const INSPECTION_CANONICAL = {
  inspection_token: 'insp-tok-1',
  filename: 'data.csv',
  source_format: 'csv',
  headers: ['province_code','indicator_code','value','reference_year','dataset_name'],
  columns: [
    { name: 'province_code', inferred_type: 'string', sample_values: ['CP'], nullable: false, position: 1 },
  ],
  direct_schema_match: true,
  suggested_mappings: [],
  warnings: [],
}

const INSPECTION_ARBITRARY = {
  inspection_token: 'insp-tok-2',
  filename: 'orders.csv',
  source_format: 'csv',
  headers: ['order_id', 'product', 'qty'],
  columns: [
    { name: 'order_id', inferred_type: 'integer', sample_values: ['1001'], nullable: false, position: 1 },
    { name: 'product', inferred_type: 'string', sample_values: ['Widget'], nullable: false, position: 2 },
    { name: 'qty', inferred_type: 'integer', sample_values: ['5'], nullable: false, position: 3 },
  ],
  direct_schema_match: false,
  suggested_mappings: [],
  warnings: [],
}

// ---------------------------------------------------------------------------
// Task 8A — Inspection flow tests
// ---------------------------------------------------------------------------

describe('ImportPage — inspection flow (Task 8A)', () => {
  it('1. inspection sends FormData — inspectFile is called with the file object', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_CANONICAL)
    api.importPreview.mockResolvedValueOnce(PREVIEW_CAN_CONFIRM)
    renderImportPage()

    const file = makeFile('data.csv', 100, 'text/csv')
    pickFile(file)

    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    await waitFor(() => {
      expect(api.inspectFile).toHaveBeenCalledTimes(1)
    })
    const [calledWithFile] = api.inspectFile.mock.calls[0]
    expect(calledWithFile).toBeInstanceOf(File)
  })

  it('2. multipart field is named file — inspectFile is called with the File object', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_CANONICAL)
    api.importPreview.mockResolvedValueOnce(PREVIEW_CAN_CONFIRM)
    renderImportPage()

    const file = makeFile('test.csv', 100, 'text/csv')
    pickFile(file)

    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    await waitFor(() => {
      expect(api.inspectFile).toHaveBeenCalledWith(file)
    })
  })

  it('3. selected filename remains visible during inspecting state', async () => {
    let resolveInspect
    api.inspectFile.mockReturnValueOnce(
      new Promise((res) => { resolveInspect = res })
    )
    renderImportPage()

    const file = makeFile('mydata.csv', 100, 'text/csv')
    pickFile(file)

    // Filename visible before upload
    expect(screen.getByText('mydata.csv')).toBeInTheDocument()

    const uploadBtn = screen.getByRole('button', { name: /upload/i })
    fireEvent.click(uploadBtn)

    // While inspecting, filename still visible
    await waitFor(() => {
      expect(screen.getByText('mydata.csv')).toBeInTheDocument()
    })

    // Clean up the pending promise
    resolveInspect(INSPECTION_CANONICAL)
  })

  it('4. canonical file triggers inspection then preview', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_CANONICAL)
    api.importPreview.mockResolvedValueOnce(PREVIEW_CAN_CONFIRM)
    renderImportPage()

    pickFile(makeFile('canonical.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    await waitFor(() => {
      expect(api.inspectFile).toHaveBeenCalledTimes(1)
      expect(api.importPreview).toHaveBeenCalledTimes(1)
    })
  })

  it('5. arbitrary file triggers inspection only — importPreview NOT called', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
    renderImportPage()

    pickFile(makeFile('orders.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    await waitFor(() => {
      expect(api.inspectFile).toHaveBeenCalledTimes(1)
    })
    expect(api.importPreview).not.toHaveBeenCalled()
  })

  it('6. arbitrary file does not call canonical preview', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce({
      ...INSPECTION_ARBITRARY,
      direct_schema_match: false,
    })
    renderImportPage()

    pickFile(makeFile('noncanonical.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    await waitFor(() => {
      expect(api.inspectFile).toHaveBeenCalledTimes(1)
    })
    expect(api.importPreview).toHaveBeenCalledTimes(0)
  })

  it('7. mapping-required message is displayed when direct_schema_match=false', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_ARBITRARY)
    renderImportPage()

    pickFile(makeFile('orders.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    // The MappingEditor renders "Map columns" heading when mapping is required
    await waitFor(() => {
      expect(screen.getByLabelText(/column mapping editor/i)).toBeInTheDocument()
    })
  })

  it('8. detected source columns are rendered when direct_schema_match=false', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce({
      ...INSPECTION_ARBITRARY,
      headers: ['order_id', 'product', 'qty'],
    })
    renderImportPage()

    pickFile(makeFile('orders.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    await waitFor(() => {
      // Source column chips are rendered with data-testid="source-column-chip"
      const chips = screen.getAllByTestId('source-column-chip')
      const chipTexts = chips.map(c => c.textContent)
      expect(chipTexts).toContain('order_id')
      expect(chipTexts).toContain('product')
      expect(chipTexts).toContain('qty')
    })
  })

  it('9. structured backend error message is displayed', async () => {
    const user = userEvent.setup()
    const structuredError = Object.assign(new Error('Request failed with status code 422'), {
      response: {
        status: 422,
        data: {
          detail: {
            code: 'IMPORT_MALFORMED_CSV',
            message: 'CSV parsing failed',
            details: {},
          },
        },
      },
    })
    api.inspectFile.mockRejectedValueOnce(structuredError)
    renderImportPage()

    pickFile(makeFile('bad.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    await waitFor(() => {
      const alerts = screen.getAllByRole('alert')
      const messages = alerts.map(a => a.textContent)
      expect(messages.some(msg => msg.includes('CSV parsing failed'))).toBe(true)
    })
  })

  it('10. generic Axios 422 text is suppressed when structured detail is present', async () => {
    const user = userEvent.setup()
    const structuredError = Object.assign(new Error('Request failed with status code 422'), {
      response: {
        status: 422,
        data: {
          detail: {
            code: 'IMPORT_MALFORMED_CSV',
            message: 'CSV parsing failed',
            details: {},
          },
        },
      },
    })
    api.inspectFile.mockRejectedValueOnce(structuredError)
    renderImportPage()

    pickFile(makeFile('bad.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    await waitFor(() => {
      const alerts = screen.getAllByRole('alert')
      const messages = alerts.map(a => a.textContent)
      // The structured message appears
      expect(messages.some(msg => msg.includes('CSV parsing failed'))).toBe(true)
      // The raw axios message does NOT appear
      expect(messages.every(msg => !msg.includes('Request failed with status code 422'))).toBe(true)
    })
  })

  it('11. inspection loading state — upload button is disabled while inspecting', async () => {
    let resolveInspect
    api.inspectFile.mockReturnValueOnce(
      new Promise((res) => { resolveInspect = res })
    )
    renderImportPage()

    pickFile(makeFile('data.csv', 100, 'text/csv'))

    const uploadBtn = screen.getByRole('button', { name: /upload/i })
    expect(uploadBtn).not.toBeDisabled()

    fireEvent.click(uploadBtn)

    // Button should now be disabled while in-flight
    await waitFor(() => {
      expect(uploadBtn).toBeDisabled()
    })

    // Clean up
    resolveInspect(INSPECTION_CANONICAL)
  })

  it('12. duplicate submission is prevented — clicking Upload twice calls inspectFile once', async () => {
    let resolveInspect
    api.inspectFile.mockReturnValueOnce(
      new Promise((res) => { resolveInspect = res })
    )
    renderImportPage()

    pickFile(makeFile('data.csv', 100, 'text/csv'))

    const uploadBtn = screen.getByRole('button', { name: /upload/i })
    fireEvent.click(uploadBtn)
    fireEvent.click(uploadBtn)  // second click while disabled

    // Only one call despite two clicks
    expect(api.inspectFile).toHaveBeenCalledTimes(1)

    // Clean up
    resolveInspect(INSPECTION_CANONICAL)
  })

  it('13. existing preview and confirm flow remains operational (regression)', async () => {
    const user = userEvent.setup()
    api.inspectFile.mockResolvedValueOnce(INSPECTION_CANONICAL)
    api.importPreview.mockResolvedValueOnce(PREVIEW_CAN_CONFIRM)
    renderImportPage()

    pickFile(makeFile('canonical.csv', 100, 'text/csv'))
    const uploadBtn = await screen.findByRole('button', { name: /upload/i })
    await user.click(uploadBtn)

    // After canonical inspection + preview, Confirm Import button should appear
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /confirm import/i })).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /confirm import/i })).not.toBeDisabled()
  })
})
