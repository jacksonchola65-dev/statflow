import { createDashboard, createDashboardCard } from './dashboardTypes'

export const INITIAL_DASHBOARD = createDashboard({ title: 'Untitled dashboard' })

export function dashboardReducer(state, action) {
  switch (action.type) {
    case 'CREATE': {
      const nextDashboard = createDashboard({
        title: action.payload?.title || 'Untitled dashboard',
        description: action.payload?.description || '',
        cards: [],
        dirty: false,
        previewMode: false,
      })

      return nextDashboard
    }

    case 'LOAD_DASHBOARD': {
      const payload = action.payload || {}
      const cards = Array.isArray(payload.cards)
        ? payload.cards.map((card, index) => ({
            id: card.id || `card-${index}-${Date.now()}`,
            visualizationSnapshot: card.visualizationSnapshot ?? card.visualization_snapshot ?? null,
            visualizationType: card.visualizationType ?? card.visualization_type ?? 'bar',
            title: card.title || 'Visualization card',
            subtitle: card.subtitle || 'Saved from analytics workspace',
            size: card.size || 'medium',
            order: Number.isFinite(card.order) ? card.order : index,
          }))
        : []

      return createDashboard({
        id: payload.id || state.id,
        title: payload.title || 'Untitled dashboard',
        description: payload.description || '',
        cards,
        dirty: false,
        previewMode: false,
      })
    }

    case 'SET_SERVER_ID': {
      return {
        ...state,
        id: action.payload?.id || state.id,
        dirty: false,
        updatedAt: new Date().toISOString(),
      }
    }

    case 'UPDATE_METADATA': {
      const nextDashboard = {
        ...state,
        title: action.payload?.title ?? state.title,
        description: action.payload?.description ?? state.description,
        updatedAt: new Date().toISOString(),
        dirty: true,
      }

      return nextDashboard
    }

    case 'ADD_CARD': {
      const payload = action.payload || {}
      const nextCard = createDashboardCard({
        ...payload,
        order: (state.cards?.length || 0),
      })

      const nextDashboard = {
        ...state,
        cards: [...(state.cards || []), nextCard],
        updatedAt: new Date().toISOString(),
        dirty: true,
      }

      return nextDashboard
    }

    case 'REMOVE_CARD': {
      return {
        ...state,
        cards: (state.cards || []).filter((card) => card.id !== action.payload?.cardId),
        updatedAt: new Date().toISOString(),
        dirty: true,
      }
    }

    case 'MOVE_CARD': {
      const currentCards = [...(state.cards || [])]
      const cardIndex = currentCards.findIndex((card) => card.id === action.payload?.cardId)
      const nextIndex = cardIndex + (action.payload?.direction === 'up' ? -1 : 1)

      if (cardIndex < 0 || nextIndex < 0 || nextIndex >= currentCards.length) {
        return state
      }

      const [movedCard] = currentCards.splice(cardIndex, 1)
      currentCards.splice(nextIndex, 0, movedCard)

      return {
        ...state,
        cards: currentCards.map((card, order) => ({ ...card, order })),
        updatedAt: new Date().toISOString(),
        dirty: true,
      }
    }

    case 'RESIZE_CARD': {
      return {
        ...state,
        cards: (state.cards || []).map((card) => card.id === action.payload?.cardId
          ? { ...card, size: action.payload?.size || card.size }
          : card),
        updatedAt: new Date().toISOString(),
        dirty: true,
      }
    }

    case 'TOGGLE_PREVIEW': {
      return {
        ...state,
        previewMode: Boolean(action.payload?.previewMode ?? !state.previewMode),
      }
    }

    case 'RESET': {
      return createDashboard({ title: 'Untitled dashboard' })
    }

    default:
      return state
  }
}
