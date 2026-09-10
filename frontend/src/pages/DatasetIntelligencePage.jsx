import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AppShell from '../components/layout/AppShell'
import ErrorState from '../components/common/ErrorState'
import LoadingState from '../components/common/LoadingState'
import KpiGrid from '../components/dashboard/KpiGrid'
import IntelligenceVisualization from '../features/analytics/visualization/IntelligenceVisualization'
import { getDatasetIntelligence } from '../services/analyticsApi'

function formatValue(value) {
  return typeof value === 'number' ? value.toLocaleString() : String(value ?? '—')
}

export default function DatasetIntelligencePage() {
  const { datasetId } = useParams()
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    setResult(null)
    setError(null)
    getDatasetIntelligence(datasetId).then((data) => active && setResult(data)).catch((err) => active && setError(err?.detail || 'Dataset analysis is unavailable.'))
    return () => { active = false }
  }, [datasetId])

  return (
    <AppShell>
      {error && <ErrorState message={error} onRetry={() => window.location.reload()} />}
      {!error && !result && <LoadingState message="Analyzing dataset and preparing visualizations…" />}
      {result && (
        <div className="space-y-8">
          <header>
            <Link className="text-sm text-indigo-300 hover:text-indigo-200" to="/analytics">Back to datasets</Link>
            <h1 className="mt-3 text-3xl font-bold text-white">{result.dataset.name}</h1>
            <p className="mt-2 text-sm text-[var(--sf-text-muted)]">{result.dataset.row_count.toLocaleString()} rows · {result.dataset.column_count.toLocaleString()} columns · Analysis complete</p>
            <p className="mt-2 text-xs text-[var(--sf-text-muted)]">Dataset facts use {result.analysis_scope === 'FULL_DATASET' ? 'full-dataset aggregates' : result.analysis_scope.toLowerCase()} · Profile sample: {result.sample_size.toLocaleString()} of {result.total_rows.toLocaleString()} rows</p>
          </header>

          <section aria-labelledby="key-metrics-heading"><h2 id="key-metrics-heading" className="mb-4 text-xl font-semibold text-white">Key metrics</h2><KpiGrid items={result.kpis.slice(0, 8).map((kpi) => ({ label: kpi.label, value: formatValue(kpi.value), unit: kpi.unit }))} /></section>

          <section aria-labelledby="visualizations-heading"><h2 id="visualizations-heading" className="mb-4 text-xl font-semibold text-white">Recommended visualizations</h2><div className="space-y-5">{result.visualizations.map((artifact) => <article className="rounded-2xl border border-white/10 bg-white/5 p-5" key={artifact.id}><h3 className="mb-4 text-lg font-semibold text-white">{artifact.title}</h3><p className="mb-3 text-xs text-[var(--sf-text-muted)]">Source scope: {artifact.analysis_scope.toLowerCase()}</p><IntelligenceVisualization artifact={artifact} /><details className="mt-4 text-sm text-[var(--sf-text-muted)]"><summary className="cursor-pointer font-semibold text-white">How this was calculated</summary><p className="mt-2">Dimension: {artifact.dimension?.column || 'None'} · Measure: {artifact.measure?.column || 'None'} · Aggregation: {artifact.measure?.aggregation || 'None'}</p></details></article>)}</div>{result.visualizations.length === 0 && <p className="text-sm text-[var(--sf-text-muted)]">No suitable chart could be generated. Data-quality information and the table remain available.</p>}</section>

          <section aria-labelledby="insights-heading"><h2 id="insights-heading" className="mb-4 text-xl font-semibold text-white">Insights</h2><ul className="space-y-3">{result.insights.map((insight) => <li className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-white" key={insight.id}>{insight.subject || insight.metric}: {formatValue(insight.value)}</li>)}</ul></section>
          <section aria-labelledby="quality-heading"><h2 id="quality-heading" className="mb-4 text-xl font-semibold text-white">Data quality</h2><ul className="space-y-3">{result.quality_notes.map((note) => <li className="rounded-xl border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-white" key={note.id}>{note.observation}</li>)}</ul></section>
          <details className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-[var(--sf-text-muted)]"><summary className="cursor-pointer font-semibold text-white">Provenance</summary><pre className="mt-3 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(result.provenance, null, 2)}</pre></details>
        </div>
      )}
    </AppShell>
  )
}
