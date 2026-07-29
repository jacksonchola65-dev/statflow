import { describe, it, expect, beforeEach, vi } from 'vitest'
import * as analyticsApi from '../services/analyticsApi'
import api from '../services/api'

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn(),
  },
}))

describe('analyticsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls the dataset list route with limit and offset', async () => {
    api.get.mockResolvedValueOnce({ data: { items: [], total: 0, limit: 5, offset: 2, has_more: false } })

    const result = await analyticsApi.listAnalyticsDatasets({ limit: 5, offset: 2 })

    expect(api.get).toHaveBeenCalledWith('/analytics/datasets', expect.objectContaining({ params: { limit: 5, offset: 2 } }))
    expect(result.total).toBe(0)
  })

  it('fetches dataset details from the correct route', async () => {
    api.get.mockResolvedValueOnce({ data: { summary: { ingestion_job_id: 'id' } } })

    await analyticsApi.getDatasetDetails('id')

    expect(api.get).toHaveBeenCalledWith('/analytics/datasets/id', expect.objectContaining({}))
  })

  it('fetches schema, dimensions, measures, preview, and statistics from the correct routes', async () => {
    api.get.mockResolvedValue({ data: [] })

    await analyticsApi.getDatasetSchema('id')
    await analyticsApi.getDatasetDimensions('id')
    await analyticsApi.getDatasetMeasures('id')
    await analyticsApi.getDatasetPreview('id', 10)
    await analyticsApi.getDatasetStatistics('id')

    expect(api.get).toHaveBeenNthCalledWith(1, '/analytics/datasets/id/schema', expect.objectContaining({}))
    expect(api.get).toHaveBeenNthCalledWith(2, '/analytics/datasets/id/dimensions', expect.objectContaining({}))
    expect(api.get).toHaveBeenNthCalledWith(3, '/analytics/datasets/id/measures', expect.objectContaining({}))
    expect(api.get).toHaveBeenNthCalledWith(4, '/analytics/datasets/id/preview', expect.objectContaining({ params: { limit: 10 } }))
    expect(api.get).toHaveBeenNthCalledWith(5, '/analytics/datasets/id/statistics', expect.objectContaining({}))
  })

  it('clamps preview limit to the backend maximum', async () => {
    api.get.mockResolvedValueOnce({ data: { ingestion_job_id: 'id', columns: [], rows: [], limit: 50, returned_count: 0 } })

    await analyticsApi.getDatasetPreview('id', 100)

    expect(api.get).toHaveBeenCalledWith('/analytics/datasets/id/preview', expect.objectContaining({ params: { limit: 50 } }))
  })

  it('preserves normalized API error detail on failure', async () => {
    const error = new Error('Request failed')
    error.response = { data: { detail: 'Dataset list failed' } }
    api.get.mockRejectedValueOnce(error)

    await expect(analyticsApi.listAnalyticsDatasets()).rejects.toMatchObject({ detail: 'Dataset list failed' })
  })
})
