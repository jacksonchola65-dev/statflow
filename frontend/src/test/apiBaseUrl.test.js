import { beforeEach, describe, expect, it, vi } from 'vitest'

const { create } = vi.hoisted(() => ({
  create: vi.fn((config) => ({
    defaults: config,
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  })),
}))

vi.mock('axios', () => ({ default: { create } }))

describe('API base URL configuration', () => {
  beforeEach(() => {
    vi.resetModules()
    create.mockClear()
  })

  it('uses the configured API origin without duplicating the version path', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://statflow-api.onrender.com/')
    await import('../services/api.js')

    expect(create.mock.calls[0][0].baseURL).toBe('https://statflow-api.onrender.com/api/v1')
    vi.unstubAllEnvs()
  })

  it('preserves the relative API path when no origin is configured', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    await import('../services/api.js')

    expect(create.mock.calls[0][0].baseURL).toBe('/api/v1')
    vi.unstubAllEnvs()
  })
})
