import { useContext, useEffect, useMemo, useReducer, useState } from 'react'
import DashboardToolbar from './DashboardToolbar'
import DashboardMetadata from './DashboardMetadata'
import DashboardGrid from './DashboardGrid'
import DashboardPreview from './DashboardPreview'
import { AuthContext } from '../../../contexts/AuthContext'
import { dashboardReducer, INITIAL_DASHBOARD } from './dashboardReducer'
import { validateDashboard } from './dashboardValidation'
import {
  deleteDashboard,
  fetchDashboardById,
  fetchSavedDashboards,
  saveDashboard,
} from '../../../services/dashboardApi'

export default function DashboardWorkspace({ snapshot }) {
  const auth = useContext(AuthContext)
  const [dashboard, dispatch] = useReducer(dashboardReducer, INITIAL_DASHBOARD)
  const [savedDashboards, setSavedDashboards] = useState([])
  const [selectedDashboardId, setSelectedDashboardId] = useState('')
  const [saving, setSaving] = useState(false)
  const [loadingSaved, setLoadingSaved] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [deleteError, setDeleteError] = useState(null)

  const validation = useMemo(() => validateDashboard(dashboard), [dashboard])

  const refreshSavedDashboards = async () => {
    try {
      const data = await fetchSavedDashboards()
      setSavedDashboards(Array.isArray(data?.dashboards) ? data.dashboards : [])
    } catch {
      setSavedDashboards([])
    }
  }

  useEffect(() => {
    if (!auth?.isAuthenticated) {
      setSavedDashboards([])
      return
    }
    refreshSavedDashboards()
  }, [auth?.isAuthenticated])

  const handleCreateDashboard = () => {
    dispatch({ type: 'CREATE' })
    setSelectedDashboardId('')
    setSaveError(null)
    setDeleteError(null)
  }

  const handleMetadataChange = (changes) => {
    dispatch({ type: 'UPDATE_METADATA', payload: changes })
  }

  const handleAddVisualization = () => {
    if (!snapshot) return

    dispatch({
      type: 'ADD_CARD',
      payload: {
        visualizationSnapshot: snapshot,
        visualizationType: snapshot?.chartType || 'bar',
        title: snapshot?.title || 'Visualization card',
        subtitle: snapshot?.subtitle || 'Saved from analytics workspace',
        size: 'medium',
        order: dashboard.cards.length,
      },
    })
  }

  const handleRemoveCard = (cardId) => {
    dispatch({ type: 'REMOVE_CARD', payload: { cardId } })
  }

  const handleMoveCard = (cardId, direction) => {
    dispatch({ type: 'MOVE_CARD', payload: { cardId, direction } })
  }

  const handleResizeCard = (cardId, size) => {
    dispatch({ type: 'RESIZE_CARD', payload: { cardId, size } })
  }

  const handleTogglePreview = () => {
    dispatch({ type: 'TOGGLE_PREVIEW' })
  }

  const handleReset = () => {
    dispatch({ type: 'RESET' })
  }

  const handleSaveDashboard = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      const result = await saveDashboard(dashboard)
      dispatch({ type: 'SET_SERVER_ID', payload: { id: result.id } })
      dispatch({ type: 'LOAD_DASHBOARD', payload: result })
      await refreshSavedDashboards()
      setSelectedDashboardId(result.id)
    } catch (error) {
      setSaveError(error?.response?.data?.detail || 'Unable to save dashboard.')
    } finally {
      setSaving(false)
    }
  }

  const handleLoadDashboard = async () => {
    if (!selectedDashboardId) return

    setLoadingSaved(true)
    setSaveError(null)
    setDeleteError(null)
    try {
      const result = await fetchDashboardById(selectedDashboardId)
      dispatch({ type: 'LOAD_DASHBOARD', payload: result })
      setSelectedDashboardId(result.id)
    } catch (error) {
      setSaveError(error?.response?.data?.detail || 'Unable to load dashboard.')
    } finally {
      setLoadingSaved(false)
    }
  }

  const handleDeleteDashboard = async () => {
    if (!selectedDashboardId) return

    setDeleteError(null)
    try {
      await deleteDashboard(selectedDashboardId)
      setSelectedDashboardId('')
      dispatch({ type: 'RESET' })
      await refreshSavedDashboards()
    } catch (error) {
      setDeleteError(error?.response?.data?.detail || 'Unable to delete dashboard.')
    }
  }

  return (
    <section className="space-y-4">
      <DashboardToolbar
        dashboard={dashboard}
        onCreate={handleCreateDashboard}
        onTogglePreview={handleTogglePreview}
        onReset={handleReset}
        onSave={handleSaveDashboard}
        onLoad={handleLoadDashboard}
        onDelete={handleDeleteDashboard}
        selectedDashboardId={selectedDashboardId}
        savedDashboards={savedDashboards}
        onSelectDashboard={setSelectedDashboardId}
        saving={saving}
        loadingSaved={loadingSaved}
        deleteDisabled={!selectedDashboardId}
      />

      <DashboardMetadata
        dashboard={dashboard}
        onCreate={handleCreateDashboard}
        onChange={handleMetadataChange}
      />

      {!validation.valid && (
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100">
          {validation.errors.join(' ')}
        </div>
      )}

      {(saveError || deleteError) && (
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100">
          {saveError || deleteError}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-4">
          {!dashboard.previewMode ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={handleAddVisualization}
                  disabled={!snapshot}
                  className="rounded-2xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Add visualization to dashboard
                </button>
                <span className="text-sm text-[var(--sf-text-muted)]">
                  {snapshot ? 'Current visualization snapshot is ready to add.' : 'Run a visualization first to enable add-to-dashboard.'}
                </span>
              </div>

              <DashboardGrid
                dashboard={dashboard}
                onRemove={handleRemoveCard}
                onResize={handleResizeCard}
                onMove={handleMoveCard}
                previewMode={dashboard.previewMode}
              />
            </div>
          ) : (
            <DashboardPreview dashboard={dashboard} />
          )}
        </div>

        <aside className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <h3 className="text-base font-semibold text-white">Dashboard metadata panel</h3>
          <dl className="mt-3 space-y-3 text-sm text-[var(--sf-text-muted)]">
            <div>
              <dt className="font-semibold text-white">Title</dt>
              <dd>{dashboard.title}</dd>
            </div>
            <div>
              <dt className="font-semibold text-white">Description</dt>
              <dd>{dashboard.description || 'No description provided.'}</dd>
            </div>
            <div>
              <dt className="font-semibold text-white">Cards</dt>
              <dd>{dashboard.cards.length}</dd>
            </div>
            <div>
              <dt className="font-semibold text-white">Dirty</dt>
              <dd>{dashboard.dirty ? 'Yes' : 'No'}</dd>
            </div>
          </dl>
        </aside>
      </div>
    </section>
  )
}
