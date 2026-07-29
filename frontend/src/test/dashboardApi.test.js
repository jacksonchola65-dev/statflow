import { describe, it, expect, beforeEach, vi } from 'vitest'
import api from '../services/api'
import * as dashboardApi from '../../src/services/dashboardApi'

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('dashboardApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls POST for unsaved dashboard (client-only id)', async () => {
    api.post.mockResolvedValue({ data: { id: 'uuid-1' } })

    const dashboard = { id: 'dashboard-123', title: 'Foo', cards: [] }
    const result = await dashboardApi.saveDashboard(dashboard)

    expect(api.post).toHaveBeenCalledWith('/dashboards', expect.any(Object))
    expect(result).toEqual({ id: 'uuid-1' })
  })

  it('calls PUT for persisted dashboard id', async () => {
    api.put.mockResolvedValue({ data: { id: 'uuid-42' } })

    const dashboard = { id: 'uuid-42', title: 'Persisted', cards: [] }
    const result = await dashboardApi.saveDashboard(dashboard)

    expect(api.put).toHaveBeenCalledWith('/dashboards/uuid-42', expect.any(Object))
    expect(result).toEqual({ id: 'uuid-42' })
  })

  it('list/get/delete use shared api client and correct endpoints', async () => {
    api.get.mockResolvedValue({ data: { dashboards: [] } })
    await dashboardApi.fetchSavedDashboards()
    expect(api.get).toHaveBeenCalledWith('/dashboards')

    api.get.mockResolvedValue({ data: { id: 'uuid-1' } })
    await dashboardApi.fetchDashboardById('uuid-1')
    expect(api.get).toHaveBeenCalledWith('/dashboards/uuid-1')

    api.delete.mockResolvedValue({ status: 204 })
    await dashboardApi.deleteDashboard('uuid-1')
    expect(api.delete).toHaveBeenCalledWith('/dashboards/uuid-1')
  })

  it('does not log tokens or sensitive payloads (no console.log calls)', async () => {
    api.post.mockResolvedValue({ data: {} })
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {})

    await dashboardApi.saveDashboard({ title: 'x', cards: [] })

    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })
})
