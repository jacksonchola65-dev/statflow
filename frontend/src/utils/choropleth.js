/**
 * choropleth.js
 * Utility functions and constants for the Zambia province choropleth map.
 *
 * Covers:
 *  - Province name normalisation (GeoJSON → StatFlow canonical names)
 *  - Quintile bin computation from a numeric array
 *  - Colour look-up from bins
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * ColorBrewer Blues (5-class) — accessible, perceptually uniform.
 * Index 0 = lowest value, index 4 = highest value.
 */
export const PALETTE = ['#eff3ff', '#bdd7e7', '#6baed6', '#3182bd', '#08519c']

/** Neutral fill used for provinces with no data. */
export const NO_DATA_COLOR = '#e0e0e0'

/** Accent stroke colour for the selected province (orange-500). */
export const SELECTED_COLOR = '#f97316'

// ---------------------------------------------------------------------------
// Province name normalisation
// ---------------------------------------------------------------------------

/**
 * Maps known GeoJSON name variants to StatFlow canonical province names.
 * Covers geoBoundaries (shapeName) and common alternative spellings.
 */
const NAME_MAP = {
  Central:          'Central',
  Copperbelt:       'Copperbelt',
  Eastern:          'Eastern',
  Luapula:          'Luapula',
  Lusaka:           'Lusaka',
  Muchinga:         'Muchinga',
  'North Western':  'North-Western',
  NorthWestern:     'North-Western',
  'North-Western':  'North-Western',
  Northern:         'Northern',
  Southern:         'Southern',
  Western:          'Western',
}

/**
 * Normalise a raw GeoJSON province name to its StatFlow canonical form.
 *
 * @param {string | null | undefined} raw - The province name from a GeoJSON feature.
 * @returns {string} The canonical StatFlow name, or the trimmed raw value if
 *                   not found in NAME_MAP, or '' for null/undefined input.
 */
export function normaliseProvinceName(raw) {
  return NAME_MAP[raw?.trim()] ?? raw?.trim() ?? ''
}

// ---------------------------------------------------------------------------
// Bin computation (quintiles)
// ---------------------------------------------------------------------------

/**
 * Compute 5 quintile upper-bound break-points from an array of numeric values.
 *
 * The array is sorted ascending, split into 5 equal-ish parts, and the maximum
 * value of each part is returned as the upper bound for that bin.
 *
 * Edge cases:
 *  - Empty array → returns []
 *  - Fewer than 5 values → each value becomes its own bin upper bound;
 *    the last bin is repeated to fill up to 5 entries.
 *
 * @param {number[]} values - Numeric data values (need not be pre-sorted).
 * @returns {number[]} Array of exactly 5 upper-bound break-points, or [] if
 *                     the input array is empty.
 */
export function computeBins(values) {
  if (!values || values.length === 0) return []

  const sorted = [...values].sort((a, b) => a - b)
  const n = sorted.length

  // For fewer than 5 values, pad the result by repeating the last value.
  if (n < 5) {
    const bins = sorted.slice() // copy the available values
    while (bins.length < 5) {
      bins.push(sorted[sorted.length - 1])
    }
    return bins
  }

  // Quintile: pick the last element of each fifth of the sorted array.
  const bins = []
  for (let i = 0; i < 5; i++) {
    // End index of this quintile (0-based, inclusive).
    const endIndex = Math.ceil(((i + 1) / 5) * n) - 1
    bins.push(sorted[endIndex])
  }

  return bins
}

// ---------------------------------------------------------------------------
// Colour look-up
// ---------------------------------------------------------------------------

/**
 * Return the PALETTE colour that corresponds to the bin a value falls into.
 *
 * Bin assignment:
 *  value <= bins[0]  →  PALETTE[0]
 *  value <= bins[1]  →  PALETTE[1]
 *  value <= bins[2]  →  PALETTE[2]
 *  value <= bins[3]  →  PALETTE[3]
 *  value >= bins[4]  →  PALETTE[4]  (also covers values above the max)
 *
 * @param {number | null | undefined} value - The province indicator value.
 * @param {number[]} bins - The 5-element array returned by {@link computeBins}.
 * @returns {string} A hex colour string from PALETTE, or NO_DATA_COLOR when
 *                   value is null/undefined or bins is empty/null.
 */
export function getColor(value, bins) {
  if (value == null || !bins || bins.length === 0) return NO_DATA_COLOR

  for (let i = 0; i < bins.length; i++) {
    if (value <= bins[i]) return PALETTE[i]
  }

  // Value exceeds all bin boundaries → highest colour.
  return PALETTE[PALETTE.length - 1]
}
