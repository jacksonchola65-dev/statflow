import { useEffect, useState } from 'react'

// Module-level cache — shared across all component instances.
// Once the data is fetched it is never re-fetched for the lifetime of the page.
let _cachedGeoJSON = null
let _inflightPromise = null

/**
 * Fetches `/zambia-provinces.geojson` once on mount and caches the result
 * at the module level so that subsequent renders and additional component
 * instances receive the cached value without triggering a new network request.
 *
 * @returns {{ geojson: object|null, loading: boolean, error: string|null }}
 */
export function useZambiaGeoJSON() {
  const [geojson, setGeoJSON] = useState(_cachedGeoJSON)
  const [loading, setLoading] = useState(_cachedGeoJSON === null)
  const [error, setError] = useState(null)

  useEffect(() => {
    // Already cached — nothing to do.
    if (_cachedGeoJSON !== null) {
      setGeoJSON(_cachedGeoJSON)
      setLoading(false)
      return
    }

    // A fetch is already in flight — wait for it instead of starting another.
    if (_inflightPromise !== null) {
      _inflightPromise
        .then((data) => {
          setGeoJSON(data)
          setLoading(false)
        })
        .catch((err) => {
          setError(err.message ?? 'Failed to load GeoJSON')
          setLoading(false)
        })
      return
    }

    // Start a fresh fetch and store the promise so other instances can reuse it.
    _inflightPromise = fetch('/zambia-provinces.geojson').then((res) => {
      if (!res.ok) {
        throw new Error(`Failed to load GeoJSON: ${res.status} ${res.statusText}`)
      }
      return res.json()
    })

    _inflightPromise
      .then((data) => {
        _cachedGeoJSON = data
        _inflightPromise = null
        setGeoJSON(data)
        setLoading(false)
      })
      .catch((err) => {
        _inflightPromise = null
        setError(err.message ?? 'Failed to load GeoJSON')
        setLoading(false)
      })
  }, [])

  return { geojson, loading, error }
}
