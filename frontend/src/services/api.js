import axios from 'axios'
import { captureApiError } from './errorTracking.js'

/**
 * Shared Axios instance.
 * All requests are relative to /api/v1 and are proxied to the backend
 * in development via the Vite dev server proxy.
 *
 * withCredentials: true — ensures HttpOnly JWT cookie is sent automatically
 * on every request (same-origin in production, cross-origin in dev via proxy).
 */
const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10_000,
  withCredentials: true,   // sends HttpOnly JWT cookie automatically
})

// ---------------------------------------------------------------------------
// CSRF support
// ---------------------------------------------------------------------------

// CSRF header name (matches backend config: settings.CSRF_HEADER_NAME)
const CSRF_HEADER = 'X-CSRF-Token'

// Callback registry — AuthContext registers a getter so we can read
// the in-memory CSRF token without importing React hooks here.
let _getCsrfToken = () => null

export function registerCsrfTokenGetter(fn) {
  _getCsrfToken = fn
}

// CSRF interceptor: inject header on state-changing methods only
api.interceptors.request.use((config) => {
  const method = (config.method || '').toLowerCase()
  if (['post', 'put', 'patch', 'delete'].includes(method)) {
    const token = _getCsrfToken()
    if (token) {
      config.headers[CSRF_HEADER] = token
    }
  }
  return config
})

// ---------------------------------------------------------------------------
// 401 unauthenticated handler
// ---------------------------------------------------------------------------

// Callback registry — AuthContext registers a callback to clear auth state
let _onUnauthenticated = () => {}

export function registerUnauthenticatedHandler(fn) {
  _onUnauthenticated = fn
}

// 401 interceptor: clear auth state; avoid redirect loop when already on /login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    captureApiError(error)
    if (error?.response?.status === 401) {
      // Do not fire for the /auth/me startup probe (handled by AuthContext)
      // or when already on /login to avoid loops.
      const url = error?.config?.url || ''
      const alreadyOnLogin =
        typeof window !== 'undefined' &&
        window.location.pathname === '/login'
      if (!alreadyOnLogin && !url.includes('/auth/me')) {
        _onUnauthenticated()
      }
    }
    return Promise.reject(error)
  }
)

// ---------------------------------------------------------------------------
// Auth helpers (REQ-6, REQ-7.3 — task 12)
// ---------------------------------------------------------------------------

/**
 * Login with email and password.
 *
 * POST /auth/login
 * The backend issues an HttpOnly JWT cookie on success.
 *
 * @param {string} email
 * @param {string} password
 * @returns {Promise<{ user: object, expires_in: number, csrf_token: string }>}
 */
export async function apiLogin(email, password) {
  const { data } = await api.post('/auth/login', { email, password })
  return data
}

/**
 * Fetch the currently authenticated user.
 *
 * GET /auth/me — validates the session cookie and returns the active user.
 * Called on app startup to restore the session (REQ-6.3).
 *
 * @returns {Promise<{ user: object, csrf_token: string }>}
 */
export async function fetchMe() {
  const { data } = await api.get('/auth/me')
  return data
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

/** @returns {{ status: string, service: string }} */
export async function fetchHealth() {
  const { data } = await api.get('/health')
  return data
}

// ---------------------------------------------------------------------------
// Provinces
// ---------------------------------------------------------------------------

/**
 * @returns {Promise<Array<{ id: string, code: string, name: string }>>}
 */
export async function fetchProvinces() {
  const { data } = await api.get('/provinces')
  return data
}

// ---------------------------------------------------------------------------
// Indicators
// ---------------------------------------------------------------------------

/**
 * @returns {Promise<Array<{ id: string, category_id: string, code: string, name: string, unit: string | null }>>}
 */
export async function fetchIndicators() {
  const { data } = await api.get('/indicators')
  return data
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

/**
 * Fetch province-level indicator summary.
 *
 * @param {{ indicatorId: string, referenceYear: number, datasetId?: string }} params
 * @returns {Promise<{
 *   indicator_id: string,
 *   dataset_id: string | null,
 *   reference_year: number,
 *   unit: string | null,
 *   results: Array<{ province_id: string, province_code: string, province_name: string, value: string }>
 * }>}
 */
export async function fetchIndicatorSummary({ indicatorId, referenceYear, datasetId }) {
  const params = { indicator_id: indicatorId, reference_year: referenceYear }
  if (datasetId) params.dataset_id = datasetId
  const { data } = await api.get('/analytics/indicator-summary', { params })
  return data
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Extract a user-readable message from an axios error and re-throw, preserving
 * the original `response` object so callers can inspect the HTTP status code.
 *
 * @param {unknown} error
 * @returns {never}
 */
function throwDetail(error) {
  if (error?.response?.data?.detail) {
    const detail = error.response.data.detail
    error.detail = typeof detail === 'string' ? detail : JSON.stringify(detail)
  }
  throw error
}

// ---------------------------------------------------------------------------
// CSV Import
// ---------------------------------------------------------------------------

/**
 * Upload a CSV file for validation preview.
 *
 * @param {File} file  The CSV File object selected or dropped by the user.
 * @returns {Promise<{
 *   preview_token:     string,
 *   total_rows:        number,
 *   valid_rows:        number,
 *   invalid_rows:      number,
 *   duplicate_rows:    number,
 *   conflict_rows:     number,
 *   can_confirm:       boolean,
 *   errors:            Array<{ row_number: number, column: string, raw_value: string, message: string }>,
 *   total_error_count: number,
 *   errors_truncated:  boolean,
 *   sample_records:    Array<{ row_number: number, province_code: string, indicator_code: string, value: string, reference_year: number, dataset_name: string }>,
 *   conflicts:         Array<{ dataset_name: string, indicator_id: string, province_id: string, reference_year: number }>,
 * }>}
 */
export async function importPreview(file) {
  const form = new FormData()
  form.append('file', file)

  try {
    // Ensure the request is sent as multipart/form-data and not forced
    // to the global `application/json` default header. Setting the
    // header to `undefined` allows the browser to populate the
    // correct `Content-Type` with boundary for FormData.
    const { data } = await api.post('/imports/csv/preview', form, {
      headers: { 'Content-Type': undefined },
    })
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * Upload a file for inspection and receive columns + metadata.
 *
 * @param {File} file  The CSV File object selected or dropped by the user.
 * @returns {Promise<import('../schemas').FileInspectionResponse>}
 */
export async function inspectFile(file) {
  const form = new FormData()
  form.append('file', file)

  try {
    const { data } = await api.post('/imports/files/inspect', form, {
      headers: { 'Content-Type': undefined },
    })
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * Retrieve a previously created inspection by token.
 *
 * @param {string} inspectionToken
 */
export async function fetchInspection(inspectionToken) {
  try {
    const { data } = await api.get(
      `/imports/files/inspect/${encodeURIComponent(inspectionToken)}`,
    )
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * Confirm a previously previewed CSV import.
 *
 * @param {string} previewToken  The preview_token from importPreview().
 * @returns {Promise<{
 *   imported_count:   number,
 *   datasets_created: number,
 *   dataset_ids:      string[],
 * }>}
 */
export async function importConfirm(previewToken) {
  try {
    const { data } = await api.post('/imports/csv/confirm', {
      preview_token: previewToken,
    })
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * Create a reusable import template.
 *
 * @param {{ name: string, description?: string, source_format: string, original_headers: string[], mapping_config: object }} payload
 */
export async function createImportTemplate(payload) {
  try {
    const { data } = await api.post('/imports/templates', payload)
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * List reusable import templates for the current user.
 */
export async function listImportTemplates() {
  try {
    const { data } = await api.get('/imports/templates')
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * Generate a mapped preview against a previously inspected file.
 *
 * @param {string} inspectionToken  The token returned by inspectFile().
 * @param {object} mappingConfiguration  A MappingConfiguration object.
 * @returns {Promise<{
 *   transformed_rows:    Array<object>,
 *   total_preview_rows:  number,
 *   mapped_column_count: number,
 *   original_headers:    string[],
 *   target_fields:       string[],
 * }>}
 */
export async function mapPreview(inspectionToken, mappingConfiguration) {
  try {
    const { data } = await api.post('/imports/files/map-preview', {
      inspection_token:    inspectionToken,
      mapping_config:      mappingConfiguration,
    })
    return data
  } catch (error) {
    throwDetail(error)
  }
}

export default api
