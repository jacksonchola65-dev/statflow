/**
 * Narrowly scoped tests for the CSV import API helpers:
 *   importPreview(file)
 *   importConfirm(previewToken)
 *
 * All network calls are intercepted with vi.mock so no real HTTP is sent.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { importPreview, importConfirm } from '../services/api'

// ---------------------------------------------------------------------------
// Mock axios to intercept all HTTP calls
// ---------------------------------------------------------------------------

vi.mock('axios', () => {
  const mockApi = {
    get:  vi.fn(),
    post: vi.fn(),
    create: vi.fn(),
    interceptors: {
      request:  { use: vi.fn() },
      response: { use: vi.fn() },
    },
    defaults: {},
  }
  mockApi.create = vi.fn(() => mockApi)
  return { default: mockApi }
})

// ---------------------------------------------------------------------------
// Access the shared mock instance that api.js will use
// ---------------------------------------------------------------------------

import axios from 'axios'
const mockApi = axios.create()   // returns the same mockApi object (see mock above)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PREVIEW_RESPONSE = {
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
  sample_records:    [],
  conflicts:         [],
}

const CONFIRM_RESPONSE = {
  imported_count:   3,
  datasets_created: 1,
  dataset_ids:      ['ds-uuid-1'],
}

// ---------------------------------------------------------------------------
// Tests — importPreview
// ---------------------------------------------------------------------------

describe('importPreview', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('sends POST to /imports/csv/preview', async () => {
    mockApi.post.mockResolvedValueOnce({ data: PREVIEW_RESPONSE })
    const file = new File(['a,b\n1,2'], 'test.csv', { type: 'text/csv' })

    await importPreview(file)

    expect(mockApi.post).toHaveBeenCalledTimes(1)
    const [url] = mockApi.post.mock.calls[0]
    expect(url).toBe('/imports/csv/preview')
  })

  it('sends the file as FormData under the field name "file"', async () => {
    mockApi.post.mockResolvedValueOnce({ data: PREVIEW_RESPONSE })
    const file = new File(['col1\nval1'], 'data.csv', { type: 'text/csv' })

    await importPreview(file)

    const [, body] = mockApi.post.mock.calls[0]
    expect(body).toBeInstanceOf(FormData)
    // The File should be appended under the key 'file'
    expect(body.get('file')).toBe(file)
  })

  it('does NOT pass a manual Content-Type header', async () => {
    mockApi.post.mockResolvedValueOnce({ data: PREVIEW_RESPONSE })
    const file = new File(['h\n1'], 'f.csv', { type: 'text/csv' })

    await importPreview(file)

    // Third argument (config) should either be absent or not contain
    // a Content-Type override.
    const callArgs = mockApi.post.mock.calls[0]
    const config = callArgs[2]  // axios.post(url, data, config?)
    if (config && config.headers) {
      expect(config.headers['Content-Type']).toBeUndefined()
    }
    // If no config was passed, that is also correct — no manual header.
  })

  it('returns the parsed response body', async () => {
    mockApi.post.mockResolvedValueOnce({ data: PREVIEW_RESPONSE })
    const file = new File(['x\n1'], 'x.csv', { type: 'text/csv' })

    const result = await importPreview(file)

    expect(result).toEqual(PREVIEW_RESPONSE)
    expect(result.preview_token).toBe('tok-abc-123')
    expect(result.can_confirm).toBe(true)
  })

  it('propagates backend errors (HTTP 400)', async () => {
    const error = Object.assign(new Error('Bad Request'), {
      response: {
        status: 400,
        data: { detail: 'Missing required columns: [value]' },
      },
    })
    mockApi.post.mockRejectedValueOnce(error)
    const file = new File(['a\n1'], 'bad.csv', { type: 'text/csv' })

    await expect(importPreview(file)).rejects.toThrow('Bad Request')
  })

  it('propagates backend errors (HTTP 415)', async () => {
    const error = Object.assign(new Error('Unsupported Media Type'), {
      response: {
        status: 415,
        data: { detail: 'Only .csv files are accepted.' },
      },
    })
    mockApi.post.mockRejectedValueOnce(error)

    await expect(
      importPreview(new File([''], 'data.xlsx', { type: 'application/vnd.ms-excel' }))
    ).rejects.toMatchObject({ response: { status: 415 } })
  })
})

// ---------------------------------------------------------------------------
// Tests — importConfirm
// ---------------------------------------------------------------------------

describe('importConfirm', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('sends POST to /imports/csv/confirm', async () => {
    mockApi.post.mockResolvedValueOnce({ data: CONFIRM_RESPONSE })

    await importConfirm('tok-abc-123')

    expect(mockApi.post).toHaveBeenCalledTimes(1)
    const [url] = mockApi.post.mock.calls[0]
    expect(url).toBe('/imports/csv/confirm')
  })

  it('sends the preview_token in a JSON body', async () => {
    mockApi.post.mockResolvedValueOnce({ data: CONFIRM_RESPONSE })

    await importConfirm('tok-abc-123')

    const [, body] = mockApi.post.mock.calls[0]
    expect(body).toEqual({ preview_token: 'tok-abc-123' })
  })

  it('returns the parsed response body', async () => {
    mockApi.post.mockResolvedValueOnce({ data: CONFIRM_RESPONSE })

    const result = await importConfirm('tok-abc-123')

    expect(result).toEqual(CONFIRM_RESPONSE)
    expect(result.imported_count).toBe(3)
    expect(result.datasets_created).toBe(1)
  })

  it('propagates backend errors (HTTP 404 — token expired)', async () => {
    const error = Object.assign(new Error('Not Found'), {
      response: {
        status: 404,
        data: { detail: 'Preview token not found or expired.' },
      },
    })
    mockApi.post.mockRejectedValueOnce(error)

    await expect(importConfirm('expired-tok')).rejects.toMatchObject({
      response: { status: 404 },
    })
  })

  it('propagates backend errors (HTTP 409 — conflict)', async () => {
    const error = Object.assign(new Error('Conflict'), {
      response: {
        status: 409,
        data: {
          detail: {
            message: '1 row(s) conflict with existing data.',
            conflicts: [],
          },
        },
      },
    })
    mockApi.post.mockRejectedValueOnce(error)

    await expect(importConfirm('conflict-tok')).rejects.toMatchObject({
      response: { status: 409 },
    })
  })

  it('propagates backend errors (HTTP 422 — validation errors)', async () => {
    const error = Object.assign(new Error('Unprocessable Entity'), {
      response: {
        status: 422,
        data: { detail: 'Preview contains 2 validation error(s).' },
      },
    })
    mockApi.post.mockRejectedValueOnce(error)

    await expect(importConfirm('invalid-tok')).rejects.toMatchObject({
      response: { status: 422 },
    })
  })
})
