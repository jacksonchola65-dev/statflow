import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

// Design-token hex values — Recharts style objects cannot read CSS variables
// so we reference the resolved hex values directly here.
const COLOR_BAR_DEFAULT  = '#6366f1' // --sf-accent  (indigo-500)
const COLOR_BAR_SELECTED = '#818cf8' // --sf-accent-muted (indigo-400)
const COLOR_AXIS_TICK    = '#64748b' // --sf-text-subtle (slate-500)
const COLOR_GRID         = '#ffffff0a' // near-invisible gridlines
const COLOR_AXIS_LINE    = '#ffffff12'
const COLOR_CURSOR       = '#ffffff08'

// Tooltip panel — matches --sf-surface + --sf-shadow-overlay
const TOOLTIP_STYLE = {
  backgroundColor: '#1e293b',
  border: '1px solid rgba(255,255,255,0.10)',
  borderRadius: '10px',
  boxShadow: '0 8px 32px rgba(0,0,0,0.40)',
  color: '#f1f5f9',
  fontSize: '13px',
  padding: '10px 14px',
}

// Y-axis K/M abbreviation formatter (unchanged from previous version)
function formatYAxis(v) {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000)     return `${(v / 1_000).toFixed(0)}K`
  return v
}

/**
 * ProvinceComparisonChart — polished bar chart using design tokens.
 *
 * Visual changes from previous version:
 *  - Default bar colour: #6366f1 (indigo-500) at 70 % opacity
 *  - Selected bar:        #818cf8 (indigo-400) at 100 % opacity +
 *                         2 px #a5b4fc stroke
 *  - CartesianGrid:       stroke thinned to #ffffff0a (was #ffffff12)
 *  - Tooltip:             darker surface (#1e293b), 10 px radius,
 *                         box-shadow, slightly larger padding
 *  - Bar animation:       600 ms ease-out (was Recharts default ~400 ms)
 *  - Axis tick colour:    slate-500 (#64748b) — matches --sf-text-subtle
 *  - Province code tick:  fontSize 11 px (was 12) for tighter fit
 *
 * All prop signatures, data-mapping, and filter behaviour are unchanged.
 *
 * @param {{
 *   data:             Array<{province_code: string, province_name: string, value: string}>,
 *   unit:             string,
 *   selectedProvince: string,
 * }} props
 */
export default function ProvinceComparisonChart({ data, unit, selectedProvince }) {
  const chartData = data.map((r) => ({
    name:     r.province_code,
    fullName: r.province_name,
    value:    parseFloat(r.value),
    id:       r.province_id,
  }))

  return (
    <ResponsiveContainer width="100%" height={340}>
      <BarChart
        data={chartData}
        margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
      >
        {/* Horizontal grid lines only — very faint */}
        <CartesianGrid
          strokeDasharray="3 3"
          stroke={COLOR_GRID}
          vertical={false}
        />

        {/* X-axis — province codes */}
        <XAxis
          dataKey="name"
          tick={{ fill: COLOR_AXIS_TICK, fontSize: 11, fontFamily: 'Inter, sans-serif' }}
          axisLine={{ stroke: COLOR_AXIS_LINE }}
          tickLine={false}
        />

        {/* Y-axis — abbreviated numeric values */}
        <YAxis
          tick={{ fill: COLOR_AXIS_TICK, fontSize: 11, fontFamily: 'Inter, sans-serif' }}
          axisLine={false}
          tickLine={false}
          width={44}
          tickFormatter={formatYAxis}
        />

        {/* Tooltip */}
        <Tooltip
          cursor={{ fill: COLOR_CURSOR }}
          contentStyle={TOOLTIP_STYLE}
          formatter={(value, _name, props) => [
            `${value.toLocaleString()} ${unit}`.trim(),
            props.payload.fullName,
          ]}
          labelFormatter={() => null}
          wrapperStyle={{ outline: 'none' }}
        />

        {/* Bars */}
        <Bar
          dataKey="value"
          radius={[4, 4, 0, 0]}
          maxBarSize={48}
          isAnimationActive
          animationDuration={600}
          animationEasing="ease-out"
        >
          {chartData.map((entry, index) => {
            const isSelected = selectedProvince && entry.id === selectedProvince
            return (
              <Cell
                key={index}
                fill={isSelected ? COLOR_BAR_SELECTED : COLOR_BAR_DEFAULT}
                fillOpacity={isSelected ? 1 : selectedProvince ? 0.55 : 0.70}
                stroke={isSelected ? '#a5b4fc' : 'none'}
                strokeWidth={isSelected ? 2 : 0}
              />
            )
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
