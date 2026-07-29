import { describe, it, expect } from 'vitest'
import {
  normaliseProvinceName,
  computeBins,
  getColor,
  PALETTE,
  NO_DATA_COLOR,
} from '../utils/choropleth.js'

// ---------------------------------------------------------------------------
// normaliseProvinceName
// ---------------------------------------------------------------------------

describe('normaliseProvinceName', () => {
  it.each([
    ['Central',       'Central'],
    ['Copperbelt',    'Copperbelt'],
    ['Eastern',       'Eastern'],
    ['Luapula',       'Luapula'],
    ['Lusaka',        'Lusaka'],
    ['Muchinga',      'Muchinga'],
    ['North Western', 'North-Western'],
    ['NorthWestern',  'North-Western'],
    ['North-Western', 'North-Western'],
    ['Northern',      'Northern'],
    ['Southern',      'Southern'],
    ['Western',       'Western'],
  ])('maps "%s" → "%s"', (raw, expected) => {
    expect(normaliseProvinceName(raw)).toBe(expected)
  })

  it('returns empty string for null', () => {
    expect(normaliseProvinceName(null)).toBe('')
  })

  it('returns empty string for undefined', () => {
    expect(normaliseProvinceName(undefined)).toBe('')
  })
})

// ---------------------------------------------------------------------------
// computeBins
// ---------------------------------------------------------------------------

describe('computeBins', () => {
  it('returns exactly 5 break-points for a 10-value array', () => {
    const values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    const bins = computeBins(values)
    expect(bins).toHaveLength(5)
  })

  it('break-points are in ascending order', () => {
    const values = [5, 15, 25, 35, 45, 55, 65, 75, 85, 95]
    const bins = computeBins(values)
    for (let i = 1; i < bins.length; i++) {
      expect(bins[i]).toBeGreaterThanOrEqual(bins[i - 1])
    }
  })

  it('last break-point equals the maximum value', () => {
    const values = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3]
    const bins = computeBins(values)
    expect(bins[4]).toBe(Math.max(...values))
  })

  it('returns [] for an empty array', () => {
    expect(computeBins([])).toEqual([])
  })

  it('pads to 5 entries when fewer than 5 values supplied', () => {
    const bins = computeBins([10, 20, 30])
    expect(bins).toHaveLength(5)
  })
})

// ---------------------------------------------------------------------------
// getColor
// ---------------------------------------------------------------------------

describe('getColor', () => {
  // Build a predictable set of bins from [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
  // Quintiles (10 values, 2 per bin): bins = [20, 40, 60, 80, 100]
  const bins = computeBins([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
  // bins === [20, 40, 60, 80, 100]

  describe('bin boundary values', () => {
    it('value equal to bins[0] returns PALETTE[0]', () => {
      expect(getColor(bins[0], bins)).toBe(PALETTE[0])
    })

    it('value equal to bins[1] returns PALETTE[1]', () => {
      expect(getColor(bins[1], bins)).toBe(PALETTE[1])
    })

    it('value equal to bins[2] returns PALETTE[2]', () => {
      expect(getColor(bins[2], bins)).toBe(PALETTE[2])
    })

    it('value equal to bins[3] returns PALETTE[3]', () => {
      expect(getColor(bins[3], bins)).toBe(PALETTE[3])
    })

    it('value equal to bins[4] returns PALETTE[4]', () => {
      expect(getColor(bins[4], bins)).toBe(PALETTE[4])
    })
  })

  describe('midpoint values', () => {
    it('midpoint below bins[0] returns PALETTE[0]', () => {
      expect(getColor(10, bins)).toBe(PALETTE[0])  // 10 <= 20
    })

    it('midpoint between bins[0] and bins[1] returns PALETTE[1]', () => {
      expect(getColor(30, bins)).toBe(PALETTE[1])  // 30 <= 40
    })

    it('midpoint between bins[1] and bins[2] returns PALETTE[2]', () => {
      expect(getColor(50, bins)).toBe(PALETTE[2])  // 50 <= 60
    })

    it('midpoint between bins[2] and bins[3] returns PALETTE[3]', () => {
      expect(getColor(70, bins)).toBe(PALETTE[3])  // 70 <= 80
    })

    it('midpoint between bins[3] and bins[4] returns PALETTE[4]', () => {
      expect(getColor(90, bins)).toBe(PALETTE[4])  // 90 <= 100
    })
  })

  describe('no-data cases', () => {
    it('returns NO_DATA_COLOR for null value', () => {
      expect(getColor(null, bins)).toBe(NO_DATA_COLOR)
    })

    it('returns NO_DATA_COLOR for undefined value', () => {
      expect(getColor(undefined, bins)).toBe(NO_DATA_COLOR)
    })

    it('returns NO_DATA_COLOR when bins is empty', () => {
      expect(getColor(50, [])).toBe(NO_DATA_COLOR)
    })

    it('returns NO_DATA_COLOR when bins is null', () => {
      expect(getColor(50, null)).toBe(NO_DATA_COLOR)
    })
  })
})
