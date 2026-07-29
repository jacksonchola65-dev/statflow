import { Component, useEffect, useMemo, useState } from 'react'
import { getVisualizationCompatibility, getVisualizationData } from './visualizationRules'
import KpiVisualization from './KpiVisualization'
import BarVisualization from './BarVisualization'
import LineVisualization from './LineVisualization'
import AreaVisualization from './AreaVisualization'
import PieVisualization from './PieVisualization'

function formatSeriesSummary(series) {
  return series.length > 0 ? series.join(', ') : 'None'
}

class VisualizationErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch() {
    this.setState({ hasError: true })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div role="alert" aria-live="polite" className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
          Visualization could not be rendered. The table view remains available.
        </div>
      )
    }

    return this.props.children
  }
}

function chartSelectOptions(options, currentValue, onChange, label) {
  return (
    <label className="flex min-w-[14rem] flex-1 flex-col gap-2 text-sm text-[var(--sf-text-muted)]">
      <span className="font-semibold text-white">{label}</span>
      <select
        aria-label={label}
        value={currentValue || ''}
        onChange={(event) => onChange(event.target.value || null)}
        className="rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export default function AnalyticsVisualization({ result, chartType: controlledChartType }) {
  const compatibility = useMemo(() => getVisualizationCompatibility(result), [result])
  const [chartType, setChartType] = useState(controlledChartType || compatibility.recommendedChart || compatibility.supportedChartTypes[0] || null)
  const [categoryField, setCategoryField] = useState(compatibility.defaultCategoryField)
  const [measureFields, setMeasureFields] = useState(compatibility.defaultMeasureFields)
  const [legendVisible, setLegendVisible] = useState(true)
  const [barOrientation, setBarOrientation] = useState('vertical')
  const [stackedMode, setStackedMode] = useState(false)
  const [pieCategoryField, setPieCategoryField] = useState(compatibility.defaultCategoryField)
  const [pieValueField, setPieValueField] = useState(compatibility.defaultMeasureFields[0] || null)

  const chartColumns = useMemo(() => Array.isArray(result?.columns) ? result.columns : [], [result])
  const categoryOptions = useMemo(() =>
    chartColumns
      .filter((column) => column?.role === 'dimension' || column?.dimension_eligible || column?.is_dimension)
      .map((column) => ({ value: column.identifier, label: column.label || column.display_name || column.identifier })),
  [chartColumns])
  const measureOptions = useMemo(() =>
    chartColumns
      .filter((column) => column?.role === 'measure' || column?.measure_eligible || column?.is_measure)
      .map((column) => ({ value: column.identifier, label: column.label || column.display_name || column.identifier })),
  [chartColumns])

  useEffect(() => {
    const nextChartType = controlledChartType || compatibility.recommendedChart || compatibility.supportedChartTypes[0] || null
    setChartType(nextChartType)
    setCategoryField(compatibility.defaultCategoryField)
    setPieCategoryField(compatibility.defaultCategoryField)
    setMeasureFields(Array.isArray(compatibility.defaultMeasureFields) ? compatibility.defaultMeasureFields : [])
    setPieValueField(compatibility.defaultMeasureFields?.[0] || null)
  }, [compatibility, controlledChartType])

  useEffect(() => {
    if (chartType !== 'pie') return
    if (!measureFields.includes(pieValueField)) {
      setPieValueField(measureFields[0] || null)
    }
  }, [chartType, measureFields, pieValueField])

  const safeMeasureFields = useMemo(() => (Array.isArray(measureFields) ? measureFields.filter(Boolean) : []), [measureFields])
  const safeCategoryField = categoryField || pieCategoryField || null
  const safeSeriesFields = safeMeasureFields.slice(0, 5)
  const overLimit = safeMeasureFields.length > 5

  const chartData = useMemo(() => {
    if (!chartType) return []
    const data = getVisualizationData(result, chartType, safeCategoryField, safeSeriesFields)
    return data
  }, [result, chartType, safeCategoryField, safeSeriesFields])

  const visualizationNeedsConfig = chartType === 'bar' || chartType === 'line' || chartType === 'area' || chartType === 'pie'

  if (!result) {
    return <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-sm text-[var(--sf-text-muted)]">No successful query result is available yet.</div>
  }

  if (compatibility.supportedChartTypes.length === 0) {
    return (
      <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
        Visualization is unavailable for this result shape. The table view remains available.
      </div>
    )
  }

  return (
    <section
      className="space-y-4 rounded-2xl border border-white/10 bg-white/5 p-4"
      aria-labelledby="analytics-visualization-title"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h3 id="analytics-visualization-title" className="text-base font-semibold text-white">Visualization result</h3>
          <p className="mt-1 text-sm text-[var(--sf-text-muted)]">
            Chart type: {chartType || 'Unavailable'} · Category: {safeCategoryField || 'None'} · Measures: {formatSeriesSummary(safeSeriesFields)}
          </p>
        </div>
        <p className="text-sm text-[var(--sf-text-muted)]">Rows shown: {result.row_count ?? result.returned_count ?? 0}</p>
      </div>

      {visualizationNeedsConfig && (
        <div className="grid gap-3 rounded-2xl border border-white/10 bg-slate-950/40 p-3 md:grid-cols-2 xl:grid-cols-4">
          {chartType !== 'kpi' && categoryOptions.length > 0 && chartSelectOptions(categoryOptions, safeCategoryField, setCategoryField, 'Category field')}
          {chartType !== 'kpi' && measureOptions.length > 0 && chartSelectOptions(measureOptions, safeSeriesFields[0] || null, (value) => setMeasureFields(value ? [value] : []), 'Value series')}
          {chartType === 'bar' && (
            <label className="flex min-w-[14rem] flex-1 flex-col gap-2 text-sm text-[var(--sf-text-muted)]">
              <span className="font-semibold text-white">Bar orientation</span>
              <select
                aria-label="Bar orientation"
                value={barOrientation}
                onChange={(event) => setBarOrientation(event.target.value)}
                className="rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="vertical">Vertical</option>
                <option value="horizontal">Horizontal</option>
              </select>
            </label>
          )}
          {chartType !== 'kpi' && (
            <label className="flex min-w-[14rem] flex-1 items-center gap-2 self-end rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white">
              <input
                type="checkbox"
                aria-label="Show legend"
                checked={legendVisible}
                onChange={(event) => setLegendVisible(event.target.checked)}
              />
              <span>Show legend</span>
            </label>
          )}
          {(chartType === 'line' || chartType === 'area') && (
            <label className="flex min-w-[14rem] flex-1 items-center gap-2 self-end rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-white">
              <input
                type="checkbox"
                aria-label="Enable stacked mode"
                checked={stackedMode}
                onChange={(event) => setStackedMode(event.target.checked)}
              />
              <span>Stacked mode</span>
            </label>
          )}
          {chartType === 'pie' && categoryOptions.length > 0 && chartSelectOptions(categoryOptions, pieCategoryField, setPieCategoryField, 'Pie category field')}
          {chartType === 'pie' && measureOptions.length > 0 && chartSelectOptions(measureOptions, pieValueField, setPieValueField, 'Pie value field')}
        </div>
      )}

      {overLimit && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
          Only the first five visible series are shown. Additional series were not included to keep the result readable.
        </div>
      )}

      <VisualizationErrorBoundary>
        {chartType === 'kpi' && <KpiVisualization data={chartData} />}
        {chartType === 'bar' && <BarVisualization data={chartData} orientation={barOrientation} legendVisible={legendVisible} />}
        {chartType === 'line' && <LineVisualization data={chartData} legendVisible={legendVisible} />}
        {chartType === 'area' && <AreaVisualization data={chartData} legendVisible={legendVisible} stacked={stackedMode} />}
        {chartType === 'pie' && <PieVisualization data={chartData} legendVisible={legendVisible} />}
      </VisualizationErrorBoundary>

      <div className="rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm text-[var(--sf-text-muted)]">
        <div className="font-semibold text-white">Accessible summary</div>
        <div className="mt-2">This visualization uses the {chartType} view for {result.row_count ?? result.returned_count ?? 0} result rows. Category field: {safeCategoryField || 'None'}. Selected measures: {formatSeriesSummary(safeSeriesFields)}.</div>
      </div>
    </section>
  )
}
