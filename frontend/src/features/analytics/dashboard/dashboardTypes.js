export const DASHBOARD_CARD_SIZES = ['small', 'medium', 'large']
export const SUPPORTED_VISUALIZATION_TYPES = ['kpi', 'bar', 'line', 'area', 'pie']
export const DASHBOARD_TITLE_MAX_LENGTH = 120
export const DASHBOARD_DESCRIPTION_MAX_LENGTH = 500
export const DASHBOARD_DEFAULT_TITLE = 'Untitled dashboard'

function normalizeWhitespace(value = '') {
  return String(value).replace(/\s+/g, ' ').trim()
}

export function normalizeDashboardTitle(value = '') {
  return normalizeWhitespace(value).slice(0, DASHBOARD_TITLE_MAX_LENGTH)
}

export function normalizeDashboardDescription(value = '') {
  return normalizeWhitespace(value).slice(0, DASHBOARD_DESCRIPTION_MAX_LENGTH)
}

export function createDashboard(overrides = {}) {
  const title = normalizeDashboardTitle(overrides.title || DASHBOARD_DEFAULT_TITLE)
  const description = normalizeDashboardDescription(overrides.description || '')

  return {
    id: `dashboard-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    ...overrides,
    title,
    description,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    cards: [],
    dirty: false,
    previewMode: false,
  }
}

export function createDashboardCard({
  visualizationSnapshot,
  visualizationType = 'bar',
  title = 'Visualization card',
  subtitle = 'Saved from analytics workspace',
  size = 'medium',
  order = 0,
}) {
  return {
    id: `card-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    visualizationSnapshot,
    visualizationType,
    title,
    subtitle,
    size,
    order,
  }
}
