import api from './api'

function normalizeDashboardPayload(dashboard) {
  return {
    title: dashboard?.title || 'Untitled dashboard',
    description: dashboard?.description || '',
    cards: Array.isArray(dashboard?.cards)
      ? dashboard.cards.map((card) => ({
          id: card.id,
          title: card.title,
          subtitle: card.subtitle || '',
          visualization_type: card.visualizationType || card.visualization_type || 'bar',
          size: card.size || 'medium',
          order: card.order ?? 0,
          visualization_snapshot: card.visualizationSnapshot || card.visualization_snapshot || null,
        }))
      : [],
  }
}

export async function fetchSavedDashboards() {
  const { data } = await api.get('/dashboards')
  return data
}

export async function fetchDashboardById(dashboardId) {
  const { data } = await api.get(`/dashboards/${dashboardId}`)
  return data
}

export async function saveDashboard(dashboard) {
  const payload = normalizeDashboardPayload(dashboard)
  if (dashboard?.id && !String(dashboard.id).startsWith('dashboard-')) {
    const { data } = await api.put(`/dashboards/${dashboard.id}`, payload)
    return data
  }

  const { data } = await api.post('/dashboards', payload)
  return data
}

export async function deleteDashboard(dashboardId) {
  await api.delete(`/dashboards/${dashboardId}`)
}
