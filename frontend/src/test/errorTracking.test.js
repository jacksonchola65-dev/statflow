import { beforeEach, describe, expect, it, vi } from 'vitest'

const sentryMock = vi.hoisted(() => ({
  init: vi.fn(),
  captureException: vi.fn(),
}))

vi.mock('@sentry/react', () => sentryMock)

import {
  beforeSend,
  captureApiError,
  captureExceptionOnce,
  initializeErrorTracking,
  sentryConfig,
} from '../services/errorTracking.js'

describe('frontend error tracking', () => {
  beforeEach(() => {
    sentryMock.init.mockClear()
    sentryMock.captureException.mockClear()
  })

  it('does nothing when the DSN is absent', () => {
    expect(initializeErrorTracking({})).toBe(false)
    expect(sentryMock.init).not.toHaveBeenCalled()
  })

  it('initializes private error-only capture when configured', () => {
    expect(initializeErrorTracking({
      VITE_SENTRY_DSN: 'https://public@example.invalid/1',
      VITE_SENTRY_ENVIRONMENT: 'test',
      VITE_SENTRY_RELEASE: 'release-1',
    })).toBe(true)

    const config = sentryMock.init.mock.calls[0][0]
    expect(config.sendDefaultPii).toBe(false)
    expect(config.tracesSampleRate).toBe(0)
    expect(config.profilesSampleRate).toBe(0)
    expect(config.replaysSessionSampleRate).toBe(0)
    expect(config.replaysOnErrorSampleRate).toBe(0)
    expect(config.environment).toBe('test')
    expect(config.release).toBe('release-1')
    expect(config.integrations).toEqual([])
  })

  it('scrubs request, user, breadcrumb, extra, and credential data', () => {
    const sanitized = beforeSend({
      request: { headers: { Authorization: 'Bearer jwt' }, data: 'payload' },
      user: { id: 'user-1', email: 'user@example.com' },
      breadcrumbs: [{ message: 'csrf=secret' }],
      extra: { password: 'secret', request_id: 'request-1' },
      contexts: { statflow: { request_id: 'request-1' } },
      exception: { values: [{ value: 'internal stack text' }] },
    })

    expect(sanitized.request).toBeUndefined()
    expect(sanitized.user).toBeUndefined()
    expect(sanitized.breadcrumbs).toBeUndefined()
    expect(sanitized.extra).toBeUndefined()
    expect(sanitized.contexts.statflow.request_id).toBe('request-1')
    expect(JSON.stringify(sanitized)).not.toContain('jwt')
    expect(JSON.stringify(sanitized)).not.toContain('user-1')
  })

  it('captures an unexpected error once with request context and no tag', () => {
    const error = new Error('runtime failure')
    expect(captureExceptionOnce(error, 'request-1')).toBe(true)
    expect(captureExceptionOnce(error, 'request-1')).toBe(false)
    expect(sentryMock.captureException).toHaveBeenCalledTimes(1)
    expect(sentryMock.captureException.mock.calls[0][1]).toEqual({
      contexts: { statflow: { request_id: 'request-1' } },
    })
  })

  it('suppresses expected 4xx API errors and captures 5xx once', () => {
    const expected = { response: { status: 401, headers: { 'x-request-id': 'request-401' } } }
    const unexpected = { response: { status: 503, headers: { 'x-request-id': 'request-503' } } }

    expect(captureApiError(expected)).toBe(false)
    expect(captureApiError(unexpected)).toBe(true)
    expect(captureApiError(unexpected)).toBe(false)
    expect(sentryMock.captureException).toHaveBeenCalledTimes(1)
    expect(sentryMock.captureException.mock.calls[0][1]).toEqual({
      contexts: { statflow: { request_id: 'request-503' } },
    })
  })

  it('keeps the expected configuration shape when unset', () => {
    const config = sentryConfig({})
    expect(config.dsn).toBeUndefined()
    expect(config.beforeSend).toBe(beforeSend)
  })
})
