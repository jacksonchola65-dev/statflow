import * as Sentry from '@sentry/react'

const capturedErrors = new WeakSet()

function hasSensitiveKey(key) {
  return /authorization|cookie|csrf|email|jwt|password|secret|token|user|body|data|query|string/i.test(key)
}

function sanitizeValue(value) {
  if (Array.isArray(value)) return value.map(sanitizeValue)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !hasSensitiveKey(key))
        .map(([key, item]) => [key, sanitizeValue(item)]),
    )
  }
  return value
}

export function beforeSend(event) {
  const sanitized = sanitizeValue(event)
  delete sanitized.request
  delete sanitized.user
  delete sanitized.breadcrumbs
  delete sanitized.extra
  delete sanitized.contexts?.browser
  delete sanitized.contexts?.os
  return sanitized
}

export function sentryConfig(env = import.meta.env) {
  return {
    dsn: env.VITE_SENTRY_DSN || undefined,
    environment: env.VITE_SENTRY_ENVIRONMENT || undefined,
    release: env.VITE_SENTRY_RELEASE || undefined,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    profilesSampleRate: 0,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
    integrations: [],
    beforeSend,
  }
}

export function captureExceptionOnce(error, requestId) {
  if (!error || typeof error !== 'object' || capturedErrors.has(error)) return false
  capturedErrors.add(error)
  const contexts = requestId ? { statflow: { request_id: requestId } } : undefined
  Sentry.captureException(error, contexts ? { contexts } : undefined)
  return true
}

export function initializeErrorTracking(env = import.meta.env) {
  const config = sentryConfig(env)
  if (!config.dsn) return false

  Sentry.init(config)
  window.addEventListener('error', (event) => {
    captureExceptionOnce(event.error || new Error('Unhandled browser error'))
  })
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason instanceof Error ? event.reason : new Error('Unhandled promise rejection')
    captureExceptionOnce(reason)
  })
  return true
}

export function captureApiError(error) {
  const status = error?.response?.status
  if (!status || status < 500) return false
  const requestId = error.response.headers?.['x-request-id'] || error.response.headers?.get?.('X-Request-ID')
  return captureExceptionOnce(error, requestId)
}
