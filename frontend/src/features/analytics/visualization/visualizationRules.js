const CHART_TYPES = {
  kpi: 'kpi',
  bar: 'bar',
  line: 'line',
  area: 'area',
  pie: 'pie',
}

const DATA_TYPE_ALIASES = {
  string: 'string',
  text: 'string',
  varchar: 'string',
  integer: 'integer',
  decimal: 'decimal',
  float: 'decimal',
  numeric: 'decimal',
  boolean: 'boolean',
  date: 'date',
  datetime: 'datetime',
  timestamp: 'datetime',
}

function normalizeType(value) {
  if (!value) return null
  const key = String(value).trim().toLowerCase()
  return DATA_TYPE_ALIASES[key] || key
}

function extractColumns(result) {
  return Array.isArray(result?.columns) ? result.columns : []
}

function extractRows(result) {
  return Array.isArray(result?.rows) ? result.rows : []
}

function isNumericType(type) {
  return type === 'integer' || type === 'decimal' || type === 'float' || type === 'numeric'
}

function isMeasureColumn(column) {
  return column?.role === 'measure' || column?.measure_eligible || column?.is_measure === true
}

function isDimensionColumn(column) {
  return column?.role === 'dimension' || column?.dimension_eligible || column?.is_dimension === true
}

function isTimeType(type) {
  return type === 'date' || type === 'datetime' || type === 'timestamp'
}

function getDisplayLabel(column) {
  return column?.label || column?.display_name || column?.identifier || 'Unnamed column'
}

function getColumnByIdentifier(columns, identifier) {
  return columns.find((column) => column.identifier === identifier)
}

function getNumericMeasures(columns) {
  return columns.filter((column) => isMeasureColumn(column) && isNumericType(normalizeType(column.data_type)))
}

function getCategoricalDimensions(columns) {
  return columns.filter((column) => isDimensionColumn(column) && !isNumericType(normalizeType(column.data_type)))
}

function getTimeDimensions(columns) {
  return columns.filter((column) => isDimensionColumn(column) && isTimeType(normalizeType(column.data_type)))
}

function getResultRowCount(result) {
  const rowCount = Number(result?.row_count ?? result?.returned_count ?? extractRows(result).length)
  return Number.isFinite(rowCount) ? rowCount : 0
}

function buildRecommendation({ supportedChartTypes, timeDimensions, categoricalDimensions, numericMeasures, rowCount, isAggregateOnly }) {
  if (isAggregateOnly && numericMeasures.length > 0) {
    return {
      recommendedChart: CHART_TYPES.kpi,
      recommendation: 'Recommended: KPI cards based on an aggregate-only result.',
      supportedChartTypes: [CHART_TYPES.kpi],
    }
  }

  if (timeDimensions.length > 0 && numericMeasures.length > 0 && rowCount > 1) {
    return {
      recommendedChart: CHART_TYPES.line,
      recommendation: 'Recommended: line chart based on a time dimension and numeric measure.',
      supportedChartTypes: [CHART_TYPES.line, CHART_TYPES.area],
    }
  }

  if (categoricalDimensions.length > 0 && numericMeasures.length > 0 && rowCount > 1) {
    return {
      recommendedChart: CHART_TYPES.bar,
      recommendation: 'Recommended: bar chart based on one or more categorical dimensions and numeric measures.',
      supportedChartTypes: [CHART_TYPES.bar],
    }
  }

  return {
    recommendedChart: supportedChartTypes[0] || null,
    recommendation: supportedChartTypes.length > 0
      ? 'Best fit based on the current result structure.'
      : 'No safe visualization is available for this result shape.',
    supportedChartTypes,
  }
}

export function getVisualizationCompatibility(result) {
  const columns = extractColumns(result)
  const rows = extractRows(result)
  const rowCount = getResultRowCount(result)

  const numericMeasures = getNumericMeasures(columns)
  const categoricalDimensions = getCategoricalDimensions(columns)
  const timeDimensions = getTimeDimensions(columns)
  const singleRowAggregate = rowCount === 1
  const isAggregateOnly = columns.length > 0 && columns.every((column) => isMeasureColumn(column))

  const supportedChartTypes = []
  const warnings = []

  if (!columns.length || rowCount === 0) {
    return {
      supportedChartTypes: [],
      recommendedChart: null,
      recommendation: 'No supported visualization is available for an empty result.',
      warnings: ['Result has no rows or no columns.'],
      defaultCategoryField: null,
      defaultMeasureFields: [],
      defaultSeriesField: null,
      detail: null,
    }
  }

  if (numericMeasures.length > 0 && isAggregateOnly && singleRowAggregate) {
    supportedChartTypes.push(CHART_TYPES.kpi)
  }

  if (categoricalDimensions.length > 0 && numericMeasures.length > 0 && rowCount > 1) {
    supportedChartTypes.push(CHART_TYPES.bar)
  }

  if (timeDimensions.length > 0 && numericMeasures.length > 0 && rowCount > 1) {
    supportedChartTypes.push(CHART_TYPES.line, CHART_TYPES.area)
  }

  const pieValid =
    categoricalDimensions.length === 1 &&
    numericMeasures.length === 1 &&
    rowCount > 0 &&
    rowCount <= 10 &&
    rows.every((row) => {
      const value = Number(row[numericMeasures[0].identifier])
      const categoryValue = row[categoricalDimensions[0].identifier]
      return Number.isFinite(value) && value >= 0 && categoryValue !== null && categoryValue !== undefined && categoryValue !== ''
    })

  if (pieValid) {
    const total = rows.reduce((sum, row) => sum + Number(row[numericMeasures[0].identifier]), 0)
    if (total > 0) {
      supportedChartTypes.push(CHART_TYPES.pie)
    } else {
      warnings.push('Pie chart is disabled because the total measure value is zero.')
    }
  } else if (categoricalDimensions.length === 1 && numericMeasures.length === 1) {
    warnings.push('Pie chart is disabled because the result does not satisfy the safe pie-chart shape.')
  }

  const defaultCategoryField = categoricalDimensions[0]?.identifier ?? timeDimensions[0]?.identifier ?? null
  const defaultMeasureFields = numericMeasures.map((column) => column.identifier).slice(0, 5)

  const { recommendedChart, recommendation } = buildRecommendation({
    supportedChartTypes,
    timeDimensions,
    categoricalDimensions,
    numericMeasures,
    rowCount,
    isAggregateOnly,
  })

  return {
    supportedChartTypes,
    recommendedChart,
    recommendation,
    warnings,
    defaultCategoryField,
    defaultMeasureFields,
    defaultSeriesField: numericMeasures[0]?.identifier ?? null,
    detail: {
      categories: categoricalDimensions.map((column) => getDisplayLabel(column)),
      measures: numericMeasures.map((column) => getDisplayLabel(column)),
      timeDimensions: timeDimensions.map((column) => getDisplayLabel(column)),
      rowCount,
      columns,
    },
  }
}

export function normalizeChartValue(value) {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }
  if (typeof value === 'string' && value.trim() === '') return null
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : null
}

export function getVisualizationData(result, chartType, selectedCategoryField, selectedMeasureFields) {
  const columns = extractColumns(result)
  const rows = extractRows(result)
  if (!result || !chartType || !rows.length) {
    return []
  }

  const selectedMeasures = Array.from(new Set((selectedMeasureFields || []).filter(Boolean)))
  const categoryField = selectedCategoryField || columns[0]?.identifier || null

  if (chartType === CHART_TYPES.kpi) {
    return selectedMeasures.map((measureKey) => {
      const measureColumn = getColumnByIdentifier(columns, measureKey)
      const value = rows[0]?.[measureKey]
      return {
        key: measureKey,
        label: getDisplayLabel(measureColumn),
        value,
      }
    })
  }

  if (chartType === CHART_TYPES.pie) {
    return rows.map((row) => ({
      name: String(row[categoryField] ?? 'Unknown'),
      value: normalizeChartValue(row[selectedMeasures[0]]),
    }))
  }

  return rows.map((row) => {
    const item = { name: String(row[categoryField] ?? 'Unknown') }
    selectedMeasures.forEach((measureKey) => {
      item[measureKey] = normalizeChartValue(row[measureKey])
    })
    return item
  })
}

export function formatVisualizationValue(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'
  }
  return String(value)
}
