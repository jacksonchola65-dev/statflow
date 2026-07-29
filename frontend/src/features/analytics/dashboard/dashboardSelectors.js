export function getDashboardCardLayoutClass(size = 'medium') {
  if (size === 'small') {
    return 'md:col-span-1 xl:col-span-1'
  }

  if (size === 'large') {
    return 'md:col-span-2 xl:col-span-3'
  }

  return 'md:col-span-2 xl:col-span-2'
}

export function getDashboardSummary(dashboard) {
  const cards = Array.isArray(dashboard?.cards) ? dashboard.cards : []
  return {
    cardCount: cards.length,
    previewMode: Boolean(dashboard?.previewMode),
    dirty: Boolean(dashboard?.dirty),
    title: dashboard?.title || 'Untitled dashboard',
  }
}

export function getDashboardCardStats(dashboard) {
  const cards = Array.isArray(dashboard?.cards) ? dashboard.cards : []
  return cards.reduce((accumulator, card) => {
    accumulator[card.size] = (accumulator[card.size] || 0) + 1
    return accumulator
  }, { small: 0, medium: 0, large: 0 })
}
