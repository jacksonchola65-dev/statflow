import { useEffect, useMemo, useState } from 'react'
import { fetchIndicatorSummary } from '../services/api'

/**
 * Fetches the province-level indicator summary and derives chart data.
 *
 * @param {{
 *   indicatorId: string,
 *   year: number,
 *   provinceFilter: string,
 * }} params
 */
export function useIndicatorSummary({ indicatorId, year, provinceFilter }) {
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!indicatorId) return
    setLoading(true)
    setError(null)
    setSummary(null)
    fetchIndicatorSummary({ indicatorId, referenceYear: year })
      .then(setSummary)
      .catch((err) => {
        setError(err.response?.data?.detail ?? err.message ?? 'Failed to load data')
      })
      .finally(() => setLoading(false))
  }, [indicatorId, year])

  const chartData = useMemo(() => {
    if (!summary?.results) return []
    if (provinceFilter) {
      return summary.results.filter((r) => r.province_id === provinceFilter)
    }
    return summary.results
  }, [summary, provinceFilter])

  return { summary, loading, error, chartData }
}
