import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchIndicators, fetchProvinces } from '../services/api'

const DEFAULT_INDICATOR_CODE = 'POVERTY_RATE'
const DEFAULT_YEAR = 2023

/**
 * Manages reference data (provinces + indicators) and user filter selections.
 * Exposes a retry-safe loadRefData callback to reload on error.
 */
export function useDashboardFilters() {
  const [provinces, setProvinces] = useState([])
  const [indicators, setIndicators] = useState([])
  const [refLoading, setRefLoading] = useState(true)
  const [refError, setRefError] = useState(null)

  const [selectedProvince, setSelectedProvince] = useState('')
  const [selectedIndicatorId, setSelectedIndicatorId] = useState('')
  const [selectedYear, setSelectedYear] = useState(DEFAULT_YEAR)

  // In-flight guard — prevents duplicate concurrent requests
  const loadingRef = useRef(false)

  const loadRefData = useCallback(() => {
    if (loadingRef.current) return
    loadingRef.current = true
    setRefLoading(true)
    setRefError(null)
    Promise.all([fetchProvinces(), fetchIndicators()])
      .then(([prov, ind]) => {
        setProvinces(prov)
        setIndicators(ind)
        const poverty = ind.find((i) => i.code === DEFAULT_INDICATOR_CODE)
        if (poverty) setSelectedIndicatorId(poverty.id)
      })
      .catch((err) => setRefError(err.message ?? 'Failed to load reference data'))
      .finally(() => {
        setRefLoading(false)
        loadingRef.current = false
      })
  }, [])

  useEffect(() => {
    loadRefData()
  }, [loadRefData])

  return {
    // Data
    provinces,
    indicators,
    // State
    refLoading,
    refError,
    // Selections
    selectedProvince,
    setSelectedProvince,
    selectedIndicatorId,
    setSelectedIndicatorId,
    selectedYear,
    setSelectedYear,
    // Actions
    loadRefData,
  }
}
