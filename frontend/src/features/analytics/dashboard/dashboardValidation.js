import {
  DASHBOARD_CARD_SIZES,
  DASHBOARD_DESCRIPTION_MAX_LENGTH,
  DASHBOARD_TITLE_MAX_LENGTH,
  SUPPORTED_VISUALIZATION_TYPES,
  normalizeDashboardDescription,
  normalizeDashboardTitle,
} from './dashboardTypes'

export function validateDashboardMetadata(title, description = '') {
  const errors = []
  const normalizedTitle = normalizeDashboardTitle(title)

  if (!normalizedTitle) {
    errors.push('Dashboard title is required.')
  }

  if (normalizedTitle.length > DASHBOARD_TITLE_MAX_LENGTH) {
    errors.push(`Dashboard title must be at most ${DASHBOARD_TITLE_MAX_LENGTH} characters.`)
  }

  const normalizedDescription = normalizeDashboardDescription(description)
  if (normalizedDescription.length > DASHBOARD_DESCRIPTION_MAX_LENGTH) {
    errors.push(`Dashboard description must be at most ${DASHBOARD_DESCRIPTION_MAX_LENGTH} characters.`)
  }

  return {
    normalizedTitle,
    normalizedDescription,
    errors,
  }
}

export function validateDashboard(dashboard) {
  const errors = []

  if (!dashboard || typeof dashboard !== 'object') {
    return {
      valid: false,
      errors: ['Dashboard object is invalid.'],
    }
  }

  const titleValidation = validateDashboardMetadata(dashboard?.title || '')
  if (titleValidation.errors.length > 0) {
    errors.push(...titleValidation.errors)
  }

  if (!Array.isArray(dashboard?.cards)) {
    errors.push('Dashboard cards must be an array.')
    return { valid: false, errors }
  }

  const cardIds = new Set()
  const cardSizes = new Set(DASHBOARD_CARD_SIZES)
  const supportedVisualizationTypes = new Set(SUPPORTED_VISUALIZATION_TYPES)
  const orderSequence = []

  dashboard.cards.forEach((card, index) => {
    if (!card || typeof card !== 'object') {
      errors.push(`Card at index ${index} is invalid.`)
      return
    }

    if (!card.id) {
      errors.push(`Card at index ${index} is missing an id.`)
    }

    if (cardIds.has(card.id)) {
      errors.push(`Duplicate card id detected: ${card.id}`)
    } else if (card.id) {
      cardIds.add(card.id)
    }

    if (!card.visualizationSnapshot || typeof card.visualizationSnapshot !== 'object') {
      errors.push(`Card '${card.id || index}' is missing a valid visualization reference.`)
    }

    if (!supportedVisualizationTypes.has(card.visualizationType)) {
      errors.push(`Card '${card.id || index}' must have a supported visualization type.`)
    }

    if (!cardSizes.has(card.size)) {
      errors.push(`Card '${card.id || index}' has an invalid size.`)
    }

    if (!Number.isInteger(card.order) || card.order < 0) {
      errors.push(`Card '${card.id || index}' must have a valid non-negative order.`)
    } else {
      orderSequence.push(card.order)
    }
  })

  if (orderSequence.length > 0) {
    const sorted = [...orderSequence].sort((first, second) => first - second)
    if (JSON.stringify(orderSequence) !== JSON.stringify(sorted)) {
      errors.push('Card order must be deterministic and non-duplicated.')
    }
  }

  return {
    valid: errors.length === 0,
    errors,
  }
}
