import api from './api'

/**
 * @typedef {{
 *   ingestion_job_id: string,
 *   source_name: string | null,
 *   dataset_name: string,
 *   status: string,
 *   row_count: number,
 *   column_count: number,
 *   completed_at: string | null,
 *   created_at: string,
 *   description: string | null,
 * }} DatasetSummary
 *
 * @typedef {{
 *   items: DatasetSummary[],
 *   total: number,
 *   limit: number,
 *   offset: number,
 *   has_more: boolean,
 * }} DatasetListResult
 *
 * @typedef {{
 *   identifier: string,
 *   display_name: string,
 *   inferred_type: string,
 *   nullable: boolean,
 *   ordinal_position: number,
 *   semantic_role: string | null,
 *   dimension_eligible: boolean,
 *   measure_eligible: boolean,
 *   supported_aggregations: string[],
 * }} DatasetColumnDescriptor
 *
 * @typedef {{
 *   identifier: string,
 *   display_name: string,
 *   data_type: string,
 * }} AnalyticsDimensionDescriptor
 *
 * @typedef {{
 *   identifier: string,
 *   display_name: string,
 *   data_type: string,
 *   supported_aggregations: string[],
 * }} AnalyticsMeasureDescriptor
 *
 * @typedef {{
 *   ingestion_job_id: string,
 *   columns: string[],
 *   rows: Array<Record<string, string | number | boolean | null>>,
 *   limit: number,
 *   returned_count: number,
 * }} DatasetPreviewResult
 *
 * @typedef {{
 *   ingestion_job_id: string,
 *   row_count: number,
 *   column_count: number,
 *   nullable_column_count: number,
 *   numeric_column_count: number,
 *   text_column_count: number,
 *   date_column_count: number,
 *   datetime_column_count: number,
 *   boolean_column_count: number,
 *   completed_at: string | null,
 * }} DatasetStatistics
 */

/**
 * @param {unknown} error
 * @throws {Error}
 */
function throwDetail(error) {
  if (error?.response?.data?.detail) {
    const detail = error.response.data.detail
    error.detail = typeof detail === 'string' ? detail : JSON.stringify(detail)
  }
  throw error
}

/**
 * @param {{ limit?: number, offset?: number, signal?: AbortSignal }} [options]
 * @returns {Promise<DatasetListResult>}
 */
export async function listAnalyticsDatasets({ limit = 50, offset = 0, signal } = {}) {
  try {
    const { data } = await api.get('/analytics/datasets', {
      params: { limit, offset },
      signal,
    })
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * @param {string} ingestionJobId
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<import('./api').DatasetDetails>}
 */
export async function getDatasetDetails(ingestionJobId, { signal } = {}) {
  try {
    const { data } = await api.get(`/analytics/datasets/${ingestionJobId}`, {
      signal,
    })
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * @param {string} ingestionJobId
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<DatasetColumnDescriptor[]>}
 */
export async function getDatasetSchema(ingestionJobId, { signal } = {}) {
  try {
    const { data } = await api.get(`/analytics/datasets/${ingestionJobId}/schema`, {
      signal,
    })
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * @param {string} ingestionJobId
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<AnalyticsDimensionDescriptor[]>}
 */
export async function getDatasetDimensions(ingestionJobId, { signal } = {}) {
  try {
    const { data } = await api.get(`/analytics/datasets/${ingestionJobId}/dimensions`, {
      signal,
    })
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * @param {string} ingestionJobId
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<AnalyticsMeasureDescriptor[]>}
 */
export async function getDatasetMeasures(ingestionJobId, { signal } = {}) {
  try {
    const { data } = await api.get(`/analytics/datasets/${ingestionJobId}/measures`, {
      signal,
    })
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * @param {string} ingestionJobId
 * @param {number} [limit=10]
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<DatasetPreviewResult>}
 */
export async function getDatasetPreview(ingestionJobId, limit = 10, { signal } = {}) {
  const normalizedLimit = Math.min(Math.max(limit || 10, 1), 50)
  try {
    const { data } = await api.get(`/analytics/datasets/${ingestionJobId}/preview`, {
      params: { limit: normalizedLimit },
      signal,
    })
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * @param {string} ingestionJobId
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<DatasetStatistics>}
 */
export async function getDatasetStatistics(ingestionJobId, { signal } = {}) {
  try {
    const { data } = await api.get(`/analytics/datasets/${ingestionJobId}/statistics`, {
      signal,
    })
    return data
  } catch (error) {
    throwDetail(error)
  }
}

/**
 * Execute an analytics query against the server.
 * @param {object} query - Query request object matching backend AnalyticsQuery contract
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<any>} - AnalyticsQueryResult from backend
 */
export async function executeAnalyticsQuery(query, { signal } = {}) {
  try {
    const { data } = await api.post('/analytics/query', query, { signal })
    return data
  } catch (error) {
    throwDetail(error)
  }
}
