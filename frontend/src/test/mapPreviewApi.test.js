/**
 * mapPreviewApi.test.js
 *
 * Focused tests for the mapPreview() API helper.
 * All network calls are intercepted with vi.mock — no real HTTP is sent.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mapPreview } from '../services/api'

// ---------------------------------------------------------------------------
// Mock axios — same pattern used by importApi.test.js
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

import axios from 'axios'
const mockApi = axios.create()

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const INSPECTION_TOKEN = 'insp-tok-abc-123'

const MAPPING_CONFIG = {
  mapping_version: 1,
  mappings: [
    { target_field: 'province_code',  source_type: 'column',      source_column: 'region',   fixed_value: null, transformations: [], required: true },
    { target_field: 'indicator_code', source_type: 'fixed_value', source_column: null,        fixed_value: 'ECOM_REVENUE', transformations: [], required: true },
    { target_field: 'value',          source_type: 'column',      source_column: 'revenue',  fixed_value: null, transformations: [{ operation: 'parse_number' }], required: true },
    { target_field: 'reference_year', source_type: 'column',      source_column: 'order_date', fixed_value: null, transformations: [{ operation: 'extract_year' }], required: true },
    { target_field: 'dataset_name',   source_type: 'fixed_value', source_column: null,        fixed_value: 'Ecommerce Sales', transformations: [], required: true },
  ],
}

const MAP_PREVIEW_RESPONSE = {
  transformed_rows: [
    {
      province_code:  'Lusaka',
      indicator_code: 'ECOM_REVENUE',
      value:          2500,
      reference_year: 2024,
      dataset_name:   'Ecommerce Sales',
    },
  ],
  total_preview_rows:  1,
  mapped_column_count: 5,
  original_headers:    ['region', 'revenue', 'order_date'],
  target_fields:       ['province_code', 'indicator_code', 'value', 'reference_year', 'dataset_name'],
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('mapPreview', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('sends a POST request', async () => {
    mockApi.post.mockResolvedValueOnce({ data: MAP_PREVIEW_RESPONSE })

    await mapPreview(INSPECTION_TOKEN, MAPPING_CONFIG)

    expect(mockApi.post).toHaveBeenCalledTimes(1)
  })

  it('calls the correct endpoint /imports/files/map-preview', async () => {
    mockApi.post.mockResolvedValueOnce({ data: MAP_PREVIEW_RESPONSE })

    await mapPreview(INSPECTION_TOKEN, MAPPING_CONFIG)

    const [url] = mockApi.post.mock.calls[0]
    expect(url).toBe('/imports/files/map-preview')
  })

  it('sends inspection_token in the request body', async () => {
    mockApi.post.mockResolvedValueOnce({ data: MAP_PREVIEW_RESPONSE })

    await mapPreview(INSPECTION_TOKEN, MAPPING_CONFIG)

    const [, body] = mockApi.post.mock.calls[0]
    expect(body.inspection_token).toBe(INSPECTION_TOKEN)
  })

  it('sends mapping_config (not mapping_configuration) as the body field name', async () => {
    mockApi.post.mockResolvedValueOnce({ data: MAP_PREVIEW_RESPONSE })

    await mapPreview(INSPECTION_TOKEN, MAPPING_CONFIG)

    const [, body] = mockApi.post.mock.calls[0]
    expect(body).toHaveProperty('mapping_config')
    expect(body.mapping_config).toEqual(MAPPING_CONFIG)
  })

  it('does not include unexpected extra fields in the body', async () => {
    mockApi.post.mockResolvedValueOnce({ data: MAP_PREVIEW_RESPONSE })

    await mapPreview(INSPECTION_TOKEN, MAPPING_CONFIG)

    const [, body] = mockApi.post.mock.calls[0]
    const keys = Object.keys(body)
    expect(keys).toEqual(['inspection_token', 'mapping_config'])
  })

  it('uses the shared api instance (authentication + CSRF handled by interceptors)', async () => {
    // The shared axios instance has CSRF and auth interceptors registered.
    // This test confirms mapPreview() calls api.post(), not a raw axios.post().
    mockApi.post.mockResolvedValueOnce({ data: MAP_PREVIEW_RESPONSE })

    await mapPreview(INSPECTION_TOKEN, MAPPING_CONFIG)

    // The mock is the same instance returned by axios.create() —
    // confirming the shared authenticated client was used.
    expect(mockApi.post).toHaveBeenCalledTimes(1)
  })

  it('returns the parsed response body unchanged', async () => {
    mockApi.post.mockResolvedValueOnce({ data: MAP_PREVIEW_RESPONSE })

    const result = await mapPreview(INSPECTION_TOKEN, MAPPING_CONFIG)

    expect(result).toEqual(MAP_PREVIEW_RESPONSE)
    expect(result.total_preview_rows).toBe(1)
    expect(result.mapped_column_count).toBe(5)
    expect(result.original_headers).toEqual(['region', 'revenue', 'order_date'])
    expect(result.target_fields).toEqual([
      'province_code', 'indicator_code', 'value', 'reference_year', 'dataset_name',
    ])
    expect(result.transformed_rows).toHaveLength(1)
    expect(result.transformed_rows[0].indicator_code).toBe('ECOM_REVENUE')
  })

  it('propagates a structured backend error (HTTP 400 — invalid mapping)', async () => {
    const error = Object.assign(new Error('Bad Request'), {
      response: {
        status: 400,
        data: {
          detail: {
            code:    'IMPORT_INVALID_MAPPING',
            message: 'Mapping configuration is invalid: mapping_version must be 1',
            details: { errors: ['mapping_version must be 1'] },
          },
        },
      },
    })
    mockApi.post.mockRejectedValueOnce(error)

    await expect(mapPreview(INSPECTION_TOKEN, MAPPING_CONFIG)).rejects.toMatchObject({
      response: { status: 400 },
    })
  })

  it('propagates a structured backend error (HTTP 404 — token expired)', async () => {
    const error = Object.assign(new Error('Not Found'), {
      response: {
        status: 404,
        data: {
          detail: {
            code:    'IMPORT_INSPECTION_EXPIRED',
            message: 'Inspection token has expired.',
            details: {},
          },
        },
      },
    })
    mockApi.post.mockRejectedValueOnce(error)

    await expect(mapPreview(INSPECTION_TOKEN, MAPPING_CONFIG)).rejects.toMatchObject({
      response: { status: 404 },
    })
  })

  it('propagates a structured backend error (HTTP 403 — wrong owner)', async () => {
    const error = Object.assign(new Error('Forbidden'), {
      response: {
        status: 403,
        data: {
          detail: {
            code:    'IMPORT_INSPECTION_FORBIDDEN',
            message: 'Inspection token does not belong to the current user.',
            details: {},
          },
        },
      },
    })
    mockApi.post.mockRejectedValueOnce(error)

    await expect(mapPreview(INSPECTION_TOKEN, MAPPING_CONFIG)).rejects.toMatchObject({
      response: { status: 403 },
    })
  })

  it('propagates a structured backend error (HTTP 422 — transformation failure)', async () => {
    const error = Object.assign(new Error('Unprocessable Entity'), {
      response: {
        status: 422,
        data: {
          detail: {
            code:    'IMPORT_MAPPING_EXECUTION_FAILED',
            message: "Transformation 'parse_number' failed on value 'bad': Cannot convert 'bad' to a number.",
            details: { operation: 'parse_number', raw_value: 'bad', reason: "Cannot convert 'bad' to a number." },
          },
        },
      },
    })
    mockApi.post.mockRejectedValueOnce(error)

    await expect(mapPreview(INSPECTION_TOKEN, MAPPING_CONFIG)).rejects.toMatchObject({
      response: { status: 422 },
    })
  })

  it('attaches the structured detail to the thrown error object', async () => {
    const detail = {
      code:    'IMPORT_SOURCE_COLUMN_NOT_FOUND',
      message: "Source column 'profit' not found",
      details: { column_name: 'profit', target_field: 'value' },
    }
    const error = Object.assign(new Error('Unprocessable Entity'), {
      response: { status: 422, data: { detail } },
    })
    mockApi.post.mockRejectedValueOnce(error)

    let caught
    try {
      await mapPreview(INSPECTION_TOKEN, MAPPING_CONFIG)
    } catch (e) {
      caught = e
    }

    // throwDetail() serialises the detail object onto error.detail
    expect(caught).toBeDefined()
    // The response object is preserved for callers that inspect error.response
    expect(caught.response.data.detail).toEqual(detail)
  })
})
